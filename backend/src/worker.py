import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.trace import Trace
from src.services.operators import execute
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
while True:
 Path('/tmp/worker-heartbeat').touch()
 try:
  item=q.blpop('operator-traces',timeout=2)
  if not item:continue
  run_id=int(item[1])
  with Session() as s:
   row=s.get(Trace,run_id)
   if not row or row.status!='queued':continue
   row.status='running';snapshot=row.snapshot;s.commit()
  try:
   result=execute(snapshot['dataset'],snapshot['plan']['steps'])
   with Session() as s:r=s.get(Trace,run_id);r.result=result;r.status='completed';s.commit()
   log('worker','trace.completed',str(run_id))
  except Exception as exc:
   logging.exception('trace failed')
   with Session() as s:r=s.get(Trace,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
 except Exception:logging.exception('worker loop');time.sleep(2)
