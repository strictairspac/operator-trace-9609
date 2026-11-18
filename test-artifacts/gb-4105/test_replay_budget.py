import os
os.environ['JWT_SECRET']='t';os.environ['DATABASE_URL']='sqlite:////tmp/replay_budget.db';os.environ['REDIS_URL']='redis://x:1/0';os.environ['SEED_DEMO']='false'
import sys;sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/replay_budget.db'):os.remove('/tmp/replay_budget.db')
from src.config.database import Base,engine,Session
import src.models.dataset, src.models.plan, src.models.trace
from src.models.replay import ReplayJob,ReplayTrial
from src.services import replay,replay_engine as eng
class FakeRedis:
 def __init__(s):s.items=[]
 def rpush(s,k,v):s.items.append((k,int(v)))
 def ping(s):return True
replay.queue=FakeRedis()
Base.metadata.create_all(engine)

def make_job(combos,matched_idx):
 with Session() as s:
  j=ReplayJob(name='j-'+str(matched_idx),base_trace_id=1,target_trace_id=2,status='queued',
    snapshot={},changed_sensor_ids=[1],combinations=[list(c) for c in combos],total_combinations=len(combos))
  s.add(j);s.flush()
  for i,c in enumerate(combos):
   s.add(ReplayTrial(job_id=j.id,combo_idx=i,sensor_ids=list(c),set_size=len(c),status='pending'))
  s.commit();jid=j.id
 # simulate worker outcomes without running operators: drive the ledger directly
 with Session() as s:
  j=s.get(ReplayJob,jid)
  for i in range(len(combos)):
   t=s.query(ReplayTrial).filter_by(job_id=jid,combo_idx=i).one()
   t.status='done';t.attempts=1;t.matched=1 if i==matched_idx else 0
   j.executed_combinations+=1
  replay._finalize(s,j);s.commit()
 return replay.detail(jid)

# Case A: 64-combo budget, no reproducing combination at all -> exhausted.
combos=eng.plan_combinations(list(range(1,9)))  # exactly 64, all small subsets
assert len(combos)==64
d=make_job(combos,matched_idx=-1)
assert d['status']=='exhausted',d['status']
print('64 combos, no match -> exhausted')

# Case B: first match appears at the very last scheduled combo; all smaller done -> proven.
d=make_job(combos,matched_idx=63)
assert d['status']=='proven' and d['proven_combo_idx']==63
print('match at last scheduled combo, all smaller ruled out -> proven')

# Case C: mid-run candidate: a match recorded while a strictly smaller combo still pending.
with Session() as s:
 j=ReplayJob(name='j-mid',base_trace_id=1,target_trace_id=2,status='running',snapshot={},
   changed_sensor_ids=[1,2],combinations=[[],[1],[2],[1,2]],total_combinations=4)
 s.add(j);s.flush()
 specs=[(0,'done',0),(1,'pending',None),(2,'done',0),(3,'done',1)]
 for i,st,m in specs:
  s.add(ReplayTrial(job_id=j.id,combo_idx=i,sensor_ids=[[],[1],[2],[1,2]][i],set_size=len([[],[1],[2],[1,2]][i]),status=st,matched=m))
 s.commit();jid=j.id
with Session() as s:
 j=s.get(ReplayJob,jid);replay._finalize(s,j);s.commit()
 d=replay.detail(jid)
 assert d['status']=='candidate' and d['proven_sensor_ids'] is None and d['candidate_combo_idx']==3
print('match found while a smaller combo pending -> candidate (not proven)')
# once the smaller combo completes as a miss, minimality is established -> proven
with Session() as s:
 t=s.query(ReplayTrial).filter_by(job_id=jid,combo_idx=1).one();t.status='done';t.matched=0
 j=s.get(ReplayJob,jid);replay._finalize(s,j);s.commit()
 d=replay.detail(jid)
 assert d['status']=='proven' and sorted(d['proven_sensor_ids'])==[1,2]
print('smaller combo ruled out -> promoted candidate to proven')
print('ALL BUDGET/STATE TESTS PASSED')
