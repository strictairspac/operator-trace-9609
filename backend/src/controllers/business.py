from src.services import datasets,plans,traces,replay
from src.services.replay_engine import ReplayValidationError
from src.services.audit import log
from fastapi import HTTPException
def save_dataset(data,user,item_id=None):
 row=datasets.save(data,item_id);log(user.email,'dataset.save',row['name']);return row
def save_plan(data,user,item_id=None):
 row=plans.save(data,item_id);log(user.email,'plan.save',row['name']);return row
def start_trace(data,user):
 row=traces.create(data);log(user.email,'trace.queue',row['name']);return row
def _guard(fn):
 try:return fn()
 except ReplayValidationError as exc:raise HTTPException(400,str(exc))
def precheck_replay(data,user):
 return _guard(lambda:replay.precheck(data.base_trace_id,data.target_trace_id))
def start_replay(data,user):
 row=_guard(lambda:replay.create(data));log(user.email,'replay.queue',row['name']);return row
def resume_replay(item_id,user):
 row=replay.requeue_stuck(item_id);log(user.email,'replay.resume',row['name']);return row
