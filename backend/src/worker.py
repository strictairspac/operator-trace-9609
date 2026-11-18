import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.trace import Trace
from src.services.operators import execute
from src.services.replay import run_job, QUEUE_KEY
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
def run_trace(run_id):
 with Session() as s:
  row=s.get(Trace,run_id)
  if not row or row.status!='queued':return
  row.status='running';snapshot=row.snapshot;s.commit()
 try:
  result=execute(snapshot['dataset'],snapshot['plan']['steps'])
  with Session() as s:r=s.get(Trace,run_id);r.result=result;r.status='completed';s.commit()
  log('worker','trace.completed',str(run_id))
 except Exception as exc:
  logging.exception('trace failed')
  with Session() as s:r=s.get(Trace,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
def main():
 while True:
  Path('/tmp/worker-heartbeat').touch()
  try:
   # Pop from either queue; traces keep their original key and ordering.
   item=q.blpop(['operator-traces',QUEUE_KEY],timeout=2)
   if not item:continue
   key,payload=item[0].decode(),int(item[1])
   if key==QUEUE_KEY:
    try:run_job(payload)
    except Exception:logging.exception('replay job loop failed for %s',payload)
   else:
    run_trace(payload)
  except Exception:logging.exception('worker loop');time.sleep(2)
if __name__=='__main__':main()
