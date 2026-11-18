import sys
sys.path.insert(0, '/workspace/backend')
from src.services import replay_engine as e

# Build two archives: 4 sensors, target overwrote reading groups of sensors 2 and 4.
sensors = [
 {'sensor_id': 1, 'zone': '北场', 'device_type': 'pump'},
 {'sensor_id': 2, 'zone': '南场', 'device_type': 'motor'},
 {'sensor_id': 3, 'zone': '试验间', 'device_type': 'valve'},
 {'sensor_id': 4, 'zone': '北场', 'device_type': 'pump'},
]
def readings(overrides=None):
 overrides = overrides or {}
 out = []
 for sid in (1, 2, 3, 4):
   for k in range(3):
     v = overrides.get(sid, 40 + sid * 5 + k)
     out.append({'sensor_id': sid, 'value': float(v + (k if sid not in overrides else 0)),
                 'recorded_at': f'2026-11-17T0{8+k}:00:00'})
 return out
base_readings = readings()
tgt_readings = readings({2: 70.0, 4: 80.0})
steps = [
 {'op': 'scan', 'source': 'readings'},
 {'op': 'filter', 'field': 'value', 'compare': 'gte', 'value': 50},
 {'op': 'hash_join', 'right': 'sensors', 'left_key': 'sensor_id', 'right_key': 'sensor_id'},
 {'op': 'keys', 'keys': ['zone'], 'measure': 'value', 'aggregate': 'avg'} if False else
 {'op': 'group', 'keys': ['zone'], 'measure': 'value', 'aggregate': 'avg'},
]
base_ds = {'name': 'b', 'description': '', 'sensors': sensors, 'readings': base_readings}
tgt_ds = {'name': 't', 'description': '', 'sensors': sensors, 'readings': tgt_readings}

def trace(ds, tid, status='completed'):
 res = e.execute(ds, steps)
 return {'id': tid, 'status': status, 'result': res,
         'snapshot': {'dataset': ds, 'plan': {'id': 1, 'steps': steps}}}

b = trace(base_ds, 1)
t = trace(tgt_ds, 2)

# 1. changed sensors exactly {2,4}
changed = e.changed_sensors(base_ds, tgt_ds)
assert changed == [2, 4], changed
print('changed sensors:', changed)

# 2. validation: same steps + sensors passes
bd, td, st = e.validate_archives(b, t)
assert st == steps

# 3. validation rejects differing steps / sensors / incomplete
bad = trace(tgt_ds, 3)
bad['snapshot']['plan']['steps'] = steps[:-1]
for case, bt, tt in [
  ('diff steps', b, bad),
  ('incomplete', b, trace(tgt_ds, 4, status='running')),
  ('same id', b, b),
]:
  try:
    e.validate_archives(bt, tt); raise AssertionError('should reject ' + case)
  except e.ReplayValidationError as ex:
    print('reject', case, '->', ex)

bad_sensor_ds = {'name': 'x', 'description': '', 'sensors': sensors[:-1], 'readings': tgt_readings}
try:
  e.validate_archives(b, trace(bad_sensor_ds, 5)); raise AssertionError('should reject sensor mismatch')
except e.ReplayValidationError as ex:
  print('reject sensor mismatch ->', ex)

# 4. combinations smallest-first, capped at 64, empty set first
combos = e.plan_combinations(changed)
assert combos[0] == ()
sizes = [len(c) for c in combos]
assert sizes == sorted(sizes)
assert len(combos) <= 64
print('combos for 2 changed:', combos)

# 5. full replacement {2,4} reproduces target; partial does not; empty does not
full = e.run_trial(base_ds, tgt_ds, steps, (2, 4))
assert e.matches(full, t), 'full replacement must reproduce target checksum'
assert not e.matches(e.run_trial(base_ds, tgt_ds, steps, (2,)), t)
assert not e.matches(e.run_trial(base_ds, tgt_ds, steps, ()), t)
print('full-set reproduces target; singletons and empty do not -> minimum size 2')

# 6. budget cap: 8 changed -> C(8,0..) exceeds 64, truncated to 64
eight = list(range(1, 9))
c8 = e.plan_combinations(eight)
assert len(c8) == 64 and max(len(c) for c in c8) < 8
print('8-sensor budget: planned', len(c8), 'combos, max size', max(len(c) for c in c8))

# 7. whole-group replacement preserves untouched sensors byte-for-byte
patched = e.build_replayed_dataset(base_ds, e._group_readings(tgt_ds['readings']), {2})
key=lambda r: r['recorded_at']
untouched = sorted([r for r in patched['readings'] if r['sensor_id'] == 1],key=key)
assert untouched == sorted([r for r in base_readings if r['sensor_id'] == 1],key=key)
replaced = sorted([r for r in patched['readings'] if r['sensor_id'] == 2],key=key)
assert replaced == sorted([r for r in tgt_readings if r['sensor_id'] == 2],key=key)
print('whole-group swap preserves untouched groups')
print('ALL ENGINE TESTS PASSED')

# 8. whole-group swap handles a brand-new group and a cleared group
sensors8 = sensors + [{'sensor_id': 9, 'zone': '南场', 'device_type': 'motor'}]
base8 = {'name': 'b8', 'description': '', 'sensors': sensors8,
         'readings': base_readings + [{'sensor_id': 1, 'value': 55.0, 'recorded_at': '2026-11-17T11:00:00'}]}
tgt8 = {'name': 't8', 'description': '', 'sensors': sensors8,
        'readings': tgt_readings + [{'sensor_id': 9, 'value': 66.0, 'recorded_at': '2026-11-17T11:00:00'}]}
ch8 = e.changed_sensors(base8, tgt8)
assert set(ch8) == {1, 2, 4, 9}, ch8  # sensor 1 group changed (extra row), 9 added, 2/4 shifted
patched8 = e.build_replayed_dataset(base8, e._group_readings(tgt8['readings']), {9})
assert [r for r in patched8['readings'] if r['sensor_id'] == 9] == \
       [r for r in tgt8['readings'] if r['sensor_id'] == 9]
# replacing nothing keeps base exactly (no sensor-9 rows appear)
patched_empty = e.build_replayed_dataset(base8, e._group_readings(tgt8['readings']), set())
assert [r for r in patched_empty['readings'] if r['sensor_id'] == 9] == []
# a full swap reproduces the target output via the real pipeline
b8 = trace(base8, 11); t8 = trace(tgt8, 12)
full8 = e.run_trial(base8, tgt8, steps, ch8)
assert e.matches(full8, t8)
print('new/cleared group swap handled; full swap reproduces target')
print('EDGE TESTS PASSED')
