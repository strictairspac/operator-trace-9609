"""Minimum-replacement replay engine.

Given two archived traces of the *same* plan and sensor table, find the smallest
set of sensors whose reading groups, replaced wholesale with the later archive's
groups, make the original operator pipeline reproduce the later result.

The combinatorial core here is pure (no DB, no Redis) so it can be unit tested
directly. Persistence, quota accounting and the queue live in replay.py.
"""
from itertools import combinations
from src.services.operators import execute

# Hard bounds from the teaching brief: at most eight changed sensors are
# admissible, and at most sixty-four combinations may be tried per job.
MAX_CHANGED_SENSORS = 8
MAX_COMBINATIONS = 64


class ReplayValidationError(ValueError):
	"""A recoverable, user-facing precondition failure (HTTP 400)."""


def _index_sensors(sensors):
	"""Canonical sensor table keyed by sensor_id; order-independent."""
	return {s['sensor_id']: {'zone': s['zone'], 'device_type': s['device_type']} for s in sensors}


def _group_readings(readings):
	"""Group every reading of a sensor together; replacement is whole-group."""
	groups = {}
	for r in readings:
		groups.setdefault(r['sensor_id'], []).append(
			{'sensor_id': r['sensor_id'], 'value': r['value'], 'recorded_at': r['recorded_at']})
	for rows in groups.values():
		rows.sort(key=lambda r: r['recorded_at'])
	return groups


def validate_archives(base_trace, target_trace):
	"""Confirm the two archives are comparable; return parsed context or raise."""
	for label, t in (('前一次', base_trace), ('后一次', target_trace)):
		if t.get('status') != 'completed' or not t.get('result'):
			raise ReplayValidationError(f'{label}存档尚未成功执行，仅受理已完成的轨迹')
	if base_trace['id'] == target_trace['id']:
		raise ReplayValidationError('请选择两条不同的存档')
	base_plan, target_plan = base_trace['snapshot']['plan'], target_trace['snapshot']['plan']
	if base_plan.get('steps') != target_plan.get('steps'):
		raise ReplayValidationError('两次存档的算子序列不一致，仅受理算子表相同的复现请求')
	base_ds, target_ds = base_trace['snapshot']['dataset'], target_trace['snapshot']['dataset']
	if _index_sensors(base_ds['sensors']) != _index_sensors(target_ds['sensors']):
		raise ReplayValidationError('两次存档的传感器表不一致，仅受理传感器表相同的复现请求')
	return base_ds, target_ds, base_plan['steps']


def changed_sensors(base_ds, target_ds):
	"""sensor_ids whose whole reading group differs between the two archives."""
	base_groups, target_groups = _group_readings(base_ds['readings']), _group_readings(target_ds['readings'])
	ids = set(base_groups) | set(target_groups)
	diff = [sid for sid in ids if base_groups.get(sid) != target_groups.get(sid)]
	diff.sort()
	return diff


def plan_combinations(changed):
	"""Enumerate replacement subsets smallest-first, capped at MAX_COMBINATIONS.

	Returns a list of tuples of sensor_ids; index in the list is combo_idx.
	The empty set is always tried first (size 0, costs one trial).
	"""
	combos, budget = [], MAX_COMBINATIONS
	for size in range(0, len(changed) + 1):
		for subset in combinations(changed, size):
			combos.append(tuple(subset))
			if len(combos) >= budget:
				return combos
	return combos


def build_replayed_dataset(base_ds, target_groups, replace_ids):
	"""Copy the base dataset, swapping whole reading groups for chosen sensors.

	The sensor table is the universe of sensor ids: a replaced group may bring in
	readings that did not exist in the base, or clear readings the base had.
	"""
	replace_ids = set(replace_ids)
	base_groups = _group_readings(base_ds['readings'])
	readings = []
	ordered_ids = sorted({s['sensor_id'] for s in base_ds['sensors']} | set(base_groups) | set(target_groups))
	for sid in ordered_ids:
		group = target_groups.get(sid) if sid in replace_ids else base_groups.get(sid)
		if group:
			readings.extend(group)
	return {'name': base_ds['name'], 'description': base_ds.get('description', ''),
		'sensors': base_ds['sensors'], 'readings': readings}


def run_trial(base_ds, target_ds, steps, replace_ids):
	"""Execute the original plan on the patched dataset; return the checksum."""
	target_groups = _group_readings(target_ds['readings'])
	dataset = build_replayed_dataset(base_ds, target_groups, set(replace_ids))
	return execute(dataset, steps)


def matches(result, target_trace):
	"""A reproduction is defined by the canonical final-output checksum."""
	return bool(result) and result.get('checksum') == target_trace['result']['checksum']
