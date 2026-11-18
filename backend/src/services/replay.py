"""Minimum-replacement replay service: validation, persistence and resumable run."""
import logging
import redis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.trace import Trace
from src.models.replay import ReplayJob, ReplayTrial
from src.services import replay_engine as engine
from src.utils.serialization import record

QUEUE_KEY = 'operator-replays'
queue = redis.Redis.from_url(REDIS_URL)


def list_items():
	with Session() as s:
		return [record(r) for r in s.query(ReplayJob).order_by(ReplayJob.id.desc()).limit(100).all()]


def detail(item_id):
	with Session() as s:
		job = s.get(ReplayJob, item_id)
		if not job:
			raise HTTPException(404, '未找到复现试算任务')
		out = record(job)
		out['trials'] = [record(t) for t in s.query(ReplayTrial).filter_by(job_id=item_id).order_by(ReplayTrial.combo_idx).all()]
		return out


def _load_trace(s, trace_id):
	row = s.get(Trace, trace_id)
	if not row:
		raise HTTPException(404, f'未找到存档轨迹 {trace_id}')
	return record(row)


def precheck(base_trace_id, target_trace_id):
	"""Dry-run acceptance check used by the form before creating a job."""
	with Session() as s:
		base, target = _load_trace(s, base_trace_id), _load_trace(s, target_trace_id)
		base_ds, target_ds, _ = engine.validate_archives(base, target)
		changed = engine.changed_sensors(base_ds, target_ds)
		combos = engine.plan_combinations(changed)
		return {
			'base_trace_id': base['id'], 'target_trace_id': target['id'],
			'changed_sensor_ids': changed, 'changed_count': len(changed),
			'admissible': len(changed) <= engine.MAX_CHANGED_SENSORS,
			'max_changed_sensors': engine.MAX_CHANGED_SENSORS,
			'planned_combinations': len(combos), 'max_combinations': engine.MAX_COMBINATIONS,
		}


def create(data):
	with Session() as s:
		base = _load_trace(s, data.base_trace_id)
		target = _load_trace(s, data.target_trace_id)
		base_ds, target_ds, steps = engine.validate_archives(base, target)
		changed = engine.changed_sensors(base_ds, target_ds)
		if len(changed) > engine.MAX_CHANGED_SENSORS:
			raise HTTPException(400, f'有改动的传感器为 {len(changed)} 个，超过上限 {engine.MAX_CHANGED_SENSORS} 个，不予受理')
		combos = [list(c) for c in engine.plan_combinations(changed)]
		job = ReplayJob(
			name=data.name, base_trace_id=base['id'], target_trace_id=target['id'],
			status='queued',
			snapshot={'base_trace': base, 'target_trace': target, 'steps': steps},
			changed_sensor_ids=changed, combinations=combos,
			total_combinations=len(combos), executed_combinations=0,
		)
		s.add(job)
		try:
			s.flush()
		except IntegrityError:
			raise HTTPException(409, '试算任务名称已存在，请换一个名称')
		for idx, sensor_ids in enumerate(combos):
			s.add(ReplayTrial(job_id=job.id, combo_idx=idx, sensor_ids=sensor_ids,
					  set_size=len(sensor_ids), status='pending'))
		s.commit()
		s.refresh(job)
		result = record(job)
	try:
		queue.rpush(QUEUE_KEY, result['id'])
	except redis.RedisError:
		with Session() as s:
			row = s.get(ReplayJob, result['id'])
			row.status = 'failed'
			row.error = '队列不可用，请创建新任务'
			s.commit()
		raise HTTPException(503, '队列不可用，请稍后重试')
	return result


def _finalize(s, job):
	"""Reflect minimality: a match is only 'proven' once every smaller subset is ruled out."""
	trials = s.query(ReplayTrial).filter_by(job_id=job.id).order_by(ReplayTrial.combo_idx).all()
	first_match = next((t for t in trials if t.matched == 1), None)
	if first_match is None:
		# No reproducing combination yet. If nothing is left to try, the budget is spent.
		if not any(t.status in ('pending', 'running') for t in trials):
			job.status = 'exhausted'
		return
	job.candidate_sensor_ids = first_match.sensor_ids
	job.candidate_combo_idx = first_match.combo_idx
	# Minimality depends only on strictly-smaller subsets, never on larger ones.
	smaller = [t for t in trials if t.combo_idx < first_match.combo_idx]
	if all(t.status == 'done' for t in smaller):
		job.proven_sensor_ids = first_match.sensor_ids
		job.proven_combo_idx = first_match.combo_idx
		job.status = 'proven'
	else:
		# A reproducing set exists, but some smaller set is not excluded yet.
		job.status = 'candidate'


def run_job(job_id):
	"""Resumable worker entrypoint. Each combination is billed at most once."""
	with Session() as s:
		job = s.get(ReplayJob, job_id)
		if not job or job.status in ('proven', 'exhausted', 'failed'):
			return
		if job.status == 'queued':
			job.status = 'running'
		s.commit()
		base_ds = job.snapshot['base_trace']['snapshot']['dataset']
		target_ds = job.snapshot['target_trace']['snapshot']['dataset']
		steps = job.snapshot['steps']
		target_trace = job.snapshot['target_trace']

	while True:
		with Session() as s:
			job = s.get(ReplayJob, job_id)
			if not job or job.status in ('proven', 'exhausted', 'failed'):
				return
			# Skip work already done; only pending rows are ever claimed.
			trial = s.execute(
				select(ReplayTrial).where(
					ReplayTrial.job_id == job_id, ReplayTrial.status == 'pending'
				).order_by(ReplayTrial.combo_idx).limit(1)
				.with_for_update(skip_locked=True)).scalar_one_or_none()
			if trial is None:
				_finalize(s, job)
				s.commit()
				return
			trial.status = 'running'
			trial.attempts += 1
			job.current_combo_idx = trial.combo_idx
			s.commit()
			claimed_idx, claimed_ids = trial.combo_idx, list(trial.sensor_ids)
		try:
			result = engine.run_trial(base_ds, target_ds, steps, claimed_ids)
			matched = 1 if engine.matches(result, target_trace) else 0
			with Session() as s:
				t = s.query(ReplayTrial).filter_by(job_id=job_id, combo_idx=claimed_idx).one()
				t.status = 'done'
				t.matched = matched
				t.output_rows = result.get('output_rows')
				t.checksum = result.get('checksum')
				t.error = None
				job = s.get(ReplayJob, job_id)
				job.executed_combinations += 1
				if matched == 1 and job.candidate_sensor_ids is None:
					job.candidate_sensor_ids = claimed_ids
					job.candidate_combo_idx = claimed_idx
				_finalize(s, job)
				s.commit()
		except Exception as exc:  # noqa: BLE001 - keep the ledger recoverable, never double-bill
			logging.exception('replay trial %s failed', claimed_idx)
			with Session() as s:
				t = s.query(ReplayTrial).filter_by(job_id=job_id, combo_idx=claimed_idx).one()
				# Not billed: return the claim to the pool so a retry resumes it once.
				t.status = 'pending'
				t.error = str(exc)[:1000]
				job = s.get(ReplayJob, job_id)
				job.status = 'running'
				job.error = f'组合 {claimed_idx} 试算中断，可从原进度恢复：{t.error}'
				s.commit()
			if _is_transient(exc):
				return  # the queue redelivery / a resume call picks the pending row up again
			# Deterministic operator error on this dataset: fail loudly for manual review
			# rather than silently spinning; pending rows stay retryable after a fix.
			with Session() as s:
				job = s.get(ReplayJob, job_id)
				job.status = 'failed'
				s.commit()
			return


def _is_transient(exc):
	name = type(exc).__name__
	return name in ('OperationalError', 'ConnectionError', 'TimeoutError', 'RedisError')


def requeue_stuck(job_id):
	"""Recover rows/orphan jobs left 'running' by a crashed worker, then re-enqueue."""
	with Session() as s:
		job = s.get(ReplayJob, job_id)
		if not job:
			raise HTTPException(404, '未找到复现试算任务')
		stuck = s.query(ReplayTrial).filter_by(job_id=job_id, status='running').all()
		for t in stuck:
			t.status = 'pending'  # never billed: the interrupted claim returns to the pool
		if job.status in ('queued', 'running', 'candidate') and stuck:
			job.status = 'queued'
		elif job.status == 'failed':
			# A deterministic failure is only resumable once the underlying issue is fixed.
			job.status = 'queued'
		s.commit()
		again = record(job)
	try:
		queue.rpush(QUEUE_KEY, job_id)
	except redis.RedisError:
		raise HTTPException(503, '队列不可用，请稍后重试')
	return again
