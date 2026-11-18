from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, UniqueConstraint, func
from src.config.database import Base


class ReplayJob(Base):
	"""A minimum-replacement search between two archived traces."""
	__tablename__ = 'replay_jobs'
	id = Column(Integer, primary_key=True)
	name = Column(String(120), unique=True, nullable=False)
	base_trace_id = Column(Integer, ForeignKey('traces.id'), nullable=False)
	target_trace_id = Column(Integer, ForeignKey('traces.id'), nullable=False)
	status = Column(String(20), default='queued', nullable=False)
	# Immutable inputs, mirrors the trace snapshot pattern.
	snapshot = Column(JSON, nullable=False)
	# changed sensor ids, the ordered combination list and progress counters.
	changed_sensor_ids = Column(JSON, nullable=False)
	combinations = Column(JSON, nullable=False)
	total_combinations = Column(Integer, nullable=False, default=0)
	executed_combinations = Column(Integer, nullable=False, default=0)
	current_combo_idx = Column(Integer, nullable=True)
	# First matching subset, while smaller subsets may still be untested.
	candidate_sensor_ids = Column(JSON, nullable=True)
	candidate_combo_idx = Column(Integer, nullable=True)
	# Proven minimum: every smaller subset has been ruled out.
	proven_sensor_ids = Column(JSON, nullable=True)
	proven_combo_idx = Column(Integer, nullable=True)
	error = Column(String(1000), nullable=True)
	created_at = Column(DateTime, server_default=func.now())
	updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReplayTrial(Base):
	"""One tried combination. A row is the idempotency/quota ledger."""
	__tablename__ = 'replay_trials'
	__table_args__ = (UniqueConstraint('job_id', 'combo_idx', name='uq_replay_trial_combo'),)
	id = Column(Integer, primary_key=True)
	job_id = Column(Integer, ForeignKey('replay_jobs.id'), nullable=False)
	combo_idx = Column(Integer, nullable=False)
	sensor_ids = Column(JSON, nullable=False)
	set_size = Column(Integer, nullable=False)
	# pending -> running -> done / failed. Retries only ever pick pending rows,
	# so an interrupted combination is resumed once and never billed twice.
	status = Column(String(20), default='pending', nullable=False)
	matched = Column(Integer, nullable=True)
	output_rows = Column(Integer, nullable=True)
	checksum = Column(String(80), nullable=True)
	error = Column(String(1000), nullable=True)
	attempts = Column(Integer, nullable=False, default=0)
	created_at = Column(DateTime, server_default=func.now())
	updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
