# Schema v1
SQLAlchemy metadata creates users, audits, datasets, plans, traces. Natural names are unique; foreign keys reference parent entities. Each trace stores immutable JSON input snapshots. PostgreSQL persists metadata and teaching datasets; the bounded Python operators execute the plan.

## v1.1 — minimum-replacement replay
Adds `replay_jobs` and `replay_trials` (see `src/models/replay.py`), created by the same `Base.metadata.create_all` on startup/seed.

- `replay_jobs`: one search between two completed `traces`. Stores immutable `snapshot` (both trace archives + the shared steps), the admissible `changed_sensor_ids`, the smallest-first `combinations` list (capped at 64), progress counters, a `candidate_*` subset and, once every smaller subset is ruled out, a `proven_*` subset. Status flows `queued → running → candidate | proven | exhausted | failed`.
- `replay_trials`: one row per combination with a unique `(job_id, combo_idx)` constraint. `status` is `pending → running → done | failed`; the worker only ever claims `pending` rows (`SELECT ... FOR UPDATE SKIP LOCKED`), so an interrupted combination is returned to the pool and billed exactly once. This table is the resumability and quota ledger.
