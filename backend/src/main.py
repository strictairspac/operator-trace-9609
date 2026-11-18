import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from src.config.database import engine
from src.services.traces import queue
from src.routes import auth,datasets,plans,traces,audit
from src.middlewares.errors import install_errors
from src.middlewares.requests import RequestTrace
@asynccontextmanager
async def lifespan(app):
 if os.getenv('SEED_DEMO','true').lower()=='true':
  try:
   from scripts.seed_demo import seed
   seed()
  except Exception:logging.exception('seed failed; API remains available')
 yield
app=FastAPI(title='松原 · 分析算子执行剖面仪',lifespan=lifespan)
app.add_middleware(RequestTrace);install_errors(app)
for r in (auth,datasets,plans,traces,audit):app.include_router(r.router)
@app.get('/health')
def health():
 with engine.connect() as c:c.execute(text('SELECT 1'))
 queue.ping();return {'status':'ok'}
