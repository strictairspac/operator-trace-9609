import os
os.environ['JWT_SECRET'] = 'test-secret'
os.environ['DATABASE_URL'] = 'sqlite:////tmp/replay_test.db'
os.environ['REDIS_URL'] = 'redis://unused:6379/0'
os.environ['SEED_DEMO'] = 'false'

import sys
sys.path.insert(0, '/workspace/backend')

# Fresh sqlite file each run.
if os.path.exists('/tmp/replay_test.db'):
	os.remove('/tmp/replay_test.db')

from fastapi.testclient import TestClient
from src.config.database import Base, engine, Session
from src.models.identity import User
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.trace import Trace
from src.models.replay import ReplayJob, ReplayTrial
from src.services import replay, traces
from src.services.operators import execute
from src.utils.security import hash_password
import src.main as main_mod

# ---- fake redis: capture enqueued ids, never open a socket ----
class FakeRedis:
	def __init__(self): self.items = []
	def rpush(self, k, v): self.items.append((k, int(v))); return len(self.items)
	def ping(self): return True
	def blpop(self, *a, **k): return None


fake = FakeRedis()
replay.queue = fake
traces.queue = fake

Base.metadata.create_all(engine)
STEPS = [
	{'op': 'scan', 'source': 'readings'},
	{'op': 'filter', 'field': 'value', 'compare': 'gte', 'value': 50},
	{'op': 'hash_join', 'right': 'sensors', 'left_key': 'sensor_id', 'right_key': 'sensor_id'},
	{'op': 'group', 'keys': ['zone'], 'measure': 'value', 'aggregate': 'avg'},
]
SENSORS = [{'sensor_id': i, 'zone': ['北场', '南场', '试验间'][i % 3],
            'device_type': ['pump', 'motor', 'valve'][i % 3]} for i in range(1, 13)]


def make_readings(shift_ids=()):
	out = []
	for i in range(120):
		sid = i % 12 + 1
		v = round(25 + (i * 13 % 800) / 10, 1)
		if sid in shift_ids:
			v = round(v + 12.5, 1)
		out.append({'sensor_id': sid, 'value': v,
		            'recorded_at': f'2026-11-17T{8 + i // 60:02d}:{i % 60:02d}:00'})
	return out


def make_trace(name, readings, plan, tid_holder):
	ds = Dataset(name=name + '-ds', sensors=[dict(x) for x in SENSORS], readings=readings,
	             description=name)
	with Session() as s:
		s.add(ds); s.flush()
		snap_ds = {'id': ds.id, 'name': ds.name, 'description': ds.description,
		           'sensors': ds.sensors, 'readings': ds.readings}
		snap_plan = {'id': plan.id, 'name': plan.name, 'dataset_id': plan.dataset_id,
		             'steps': STEPS, 'note': plan.note}
		result = execute(snap_ds, STEPS)
		tr = Trace(name=name, plan_id=plan.id, dataset_id=ds.id, status='completed',
		           result=result, snapshot={'dataset': snap_ds, 'plan': snap_plan})
		s.add(tr); s.commit(); s.refresh(tr)
		return tr.id


with Session() as s:
	s.add(User(email='operator@operator.local', role='operator', password=hash_password('Trace2026!')))
	s.add(User(email='viewer@operator.local', role='viewer', password=hash_password('Trace2026!')))
	s.add(User(email='admin@operator.local', role='admin', password=hash_password('Trace2026!')))
	plan = Plan(name='p', dataset_id=1, steps=STEPS, note='n')
	s.add(plan); s.commit(); s.refresh(plan)

base_id = make_trace('第一次存档', make_readings(), plan, None)
target_id = make_trace('第二次存档', make_readings(shift_ids=(2, 7)), plan, None)

client = TestClient(main_mod.app)


def login(email):
	r = client.post('/auth/login', json={'email': email, 'password': 'Trace2026!'})
	assert r.status_code == 200, r.text
	return {'Authorization': 'Bearer ' + r.json()['token']}


op = login('operator@operator.local')
vw = login('viewer@operator.local')

# 1. precheck reports exactly the two changed sensors and a 4-combo plan
r = client.post('/replays/precheck', json={'base_trace_id': base_id, 'target_trace_id': target_id}, headers=op)
assert r.status_code == 200, r.text
pc = r.json()
assert pc['changed_sensor_ids'] == [2, 7], pc
assert pc['admissible'] is True and pc['planned_combinations'] == 4
print('precheck ok:', pc['changed_count'], 'changed,', pc['planned_combinations'], 'combos')

# 2. viewer cannot start a replay (403)
r = client.post('/replays', json={'name': 'forbidden', 'base_trace_id': base_id,
                                  'target_trace_id': target_id}, headers=vw)
assert r.status_code == 403, r.text
print('viewer write blocked: 403')

# 3. validation failure -> recoverable 400 (same id)
r = client.post('/replays', json={'name': 'bad', 'base_trace_id': base_id,
                                  'target_trace_id': base_id}, headers=op)
assert r.status_code == 400 and '不同的存档' in r.json()['detail']
print('recoverable validation error: 400 ->', r.json()['detail'])

# 4. create job and run it synchronously (worker logic)
r = client.post('/replays', json={'name': '复现试算-1', 'base_trace_id': base_id,
                                  'target_trace_id': target_id}, headers=op)
assert r.status_code == 200, r.text
job_id = r.json()['id']
assert fake.items[-1] == (replay.QUEUE_KEY, job_id)
replay.run_job(job_id)

detail = replay.detail(job_id)
assert detail['status'] == 'proven', detail['status']
assert sorted(detail['proven_sensor_ids']) == [2, 7]
assert detail['executed_combinations'] == 4
assert detail['total_combinations'] == 4
# only the full {2,7} combination matched
matched = [t for t in detail['trials'] if t['matched'] == 1]
assert len(matched) == 1 and sorted(matched[0]['sensor_ids']) == [2, 7]
assert all(t['status'] == 'done' and t['attempts'] == 1 for t in detail['trials'])
print('proven minimum:', detail['proven_sensor_ids'], 'after', detail['executed_combinations'], 'trials')

# 5. crash recovery + no double billing on a fresh job interrupted mid-flight.
r = client.post('/replays', json={'name': '复现试算-中断', 'base_trace_id': base_id,
                                  'target_trace_id': target_id}, headers=op)
crash_id = r.json()['id']
with Session() as s:
	j = s.get(ReplayJob, crash_id)
	j.status = 'running'; j.executed_combinations = 2
	trials = {t.combo_idx: t for t in s.query(ReplayTrial).filter_by(job_id=crash_id).all()}
	# combos 0 and 1 finished and billed once; combo 2 was in flight; combo 3 never started.
	trials[0].status = 'done'; trials[0].matched = 0; trials[0].attempts = 1
	trials[1].status = 'done'; trials[1].matched = 0; trials[1].attempts = 1
	trials[2].status = 'running'; trials[2].attempts = 1
	trials[3].status = 'pending'; trials[3].attempts = 0
	s.commit()
replay.requeue_stuck(crash_id)
replay.run_job(crash_id)
detail = replay.detail(crash_id)
by_idx = {t['combo_idx']: t for t in detail['trials']}
# finished rows are never touched again; the in-flight row is retried once, then 3 runs once.
assert by_idx[0]['attempts'] == 1 and by_idx[1]['attempts'] == 1
assert by_idx[2]['attempts'] == 2 and by_idx[3]['attempts'] == 1
assert all(t['status'] == 'done' for t in detail['trials'])
# four distinct combinations billed once each on the result ledger — not five.
assert detail['executed_combinations'] == 4
assert detail['status'] == 'proven' and sorted(detail['proven_sensor_ids']) == [2, 7]
print('resumed from interrupted progress; finished combos not re-billed, all 4 done once')

# 6. conservative candidate labeling: a smaller subset left un-ruled-out forbids 'proven'
with Session() as s:
	j = s.get(ReplayJob, job_id)
	j.status = 'running'; j.proven_sensor_ids = None
	# mark the size-1 singleton trial as not done while the full-set match stays done
	single = s.query(ReplayTrial).filter_by(job_id=job_id, combo_idx=1).one()
	single.status = 'pending'; single.matched = None
	s.commit()
with Session() as s:
	j = s.get(ReplayJob, job_id)
	replay._finalize(s, j)
	s.commit()
	assert j.status == 'candidate', j.status
	assert sorted(j.candidate_sensor_ids) == [2, 7]
print('un-ruled smaller subset forces conservative status: candidate')

# 7. >8 changed sensors rejected at create time (build a wide dataset)
wide_sensors = [{'sensor_id': i, 'zone': 'z', 'device_type': 'pump'} for i in range(1, 11)]
with Session() as s:
	dsb = Dataset(name='wide-base', sensors=[dict(x) for x in wide_sensors],
	              readings=[{'sensor_id': i, 'value': 60.0, 'recorded_at': '2026-11-17T09:00:00'} for i in range(1, 11)])
	dst = Dataset(name='wide-target', sensors=[dict(x) for x in wide_sensors],
	              readings=[{'sensor_id': i, 'value': 90.0, 'recorded_at': '2026-11-17T09:00:00'} for i in range(1, 11)])
	s.add_all([dsb, dst]); s.flush()
	wp = Plan(name='wide-plan', dataset_id=dsb.id, steps=STEPS, note='n')
	s.add(wp); s.flush()
	def tr(ds):
		snap = {'dataset': {'id': ds.id, 'name': ds.name, 'description': '', 'sensors': ds.sensors, 'readings': ds.readings},
		        'plan': {'id': wp.id, 'name': wp.name, 'dataset_id': wp.id, 'steps': STEPS, 'note': 'n'}}
		return Trace(name=ds.name + '-tr', plan_id=wp.id, dataset_id=ds.id, status='completed',
		             result=execute(snap['dataset'], STEPS), snapshot=snap)
	s.add_all([tr(dsb), tr(dst)]); s.commit()
	wb = s.query(Trace).filter_by(name='wide-base-tr').one().id
	wt = s.query(Trace).filter_by(name='wide-target-tr').one().id
r = client.post('/replays/precheck', json={'base_trace_id': wb, 'target_trace_id': wt}, headers=op)
assert r.json()['admissible'] is False and r.json()['changed_count'] == 10
r = client.post('/replays', json={'name': 'too-many', 'base_trace_id': wb, 'target_trace_id': wt}, headers=op)
assert r.status_code == 400 and '上限' in r.json()['detail']
print('10 changed sensors rejected: 400 ->', r.json()['detail'])

# 8. read endpoints work for viewer
r = client.get('/replays', headers=vw)
assert r.status_code == 200 and len(r.json()) >= 1
r = client.get(f'/replays/{job_id}', headers=vw)
assert r.status_code == 200 and 'trials' in r.json()
print('viewer read access ok; total jobs =', len(client.get('/replays', headers=op).json()))
print('ALL INTEGRATION TESTS PASSED')
