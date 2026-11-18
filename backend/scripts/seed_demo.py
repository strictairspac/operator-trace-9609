from src.config.database import Base,engine,Session
from src.models.identity import User,Audit
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.trace import Trace
from src.models.replay import ReplayJob,ReplayTrial
from src.services.operators import execute
from src.utils.security import hash_password
DEFAULT_STEPS=[{'op':'scan','source':'readings'},{'op':'filter','field':'value','compare':'gte','value':50},{'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'},{'op':'group','keys':['zone'],'measure':'value','aggregate':'avg'}]
def seed():
 Base.metadata.create_all(engine)
 with Session() as s:
  for role in ('admin','operator','viewer'):
   if not s.query(User).filter_by(email=role+'@operator.local').first():s.add(User(email=role+'@operator.local',role=role,password=hash_password('Trace2026!')))
  sensors=[{'sensor_id':i,'zone':['北场','南场','试验间'][i%3],'device_type':['pump','motor','valve'][i%3]} for i in range(1,13)]
  readings=[{'sensor_id':i%12+1,'value':round(25+(i*13%800)/10,1),'recorded_at':f'2026-11-17T{8+i//60:02d}:{i%60:02d}:00'} for i in range(240)]
  seeds=[('松原日班温升采样',sensors,readings,'240条采样 / 12个传感器 / 区域温升复核'),('空数据边界',[],[],'验证空输入和空聚合'),('重复键校验',[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':1,'zone':'复核点','device_type':'pump'}],[{'sensor_id':1,'value':80,'recorded_at':'2026-11-17T09:00:00'}],'右表重复键必须保留连接倍数')]
  for name,a,b,desc in seeds:
   if not s.query(Dataset).filter_by(name=name).first():s.add(Dataset(name=name,sensors=a,readings=b,description=desc))
  s.flush()
  for i,(name,_,_,_) in enumerate(seeds):
   pname=['过滤-连接-分组基线','空输入管线','重复键内连接'][i]
   if not s.query(Plan).filter_by(name=pname).first():s.add(Plan(name=pname,dataset_id=s.query(Dataset).filter_by(name=name).one().id,steps=DEFAULT_STEPS,note='受限DSL，Python算子真实执行'))
  s.flush()
  _seed_replay_archives(s,sensors,readings)
  s.commit();counts={m.__tablename__:s.query(m).count() for m in (User,Dataset,Plan,Trace,ReplayJob,ReplayTrial)};print(counts);return counts
def _seed_replay_archives(s,sensors,readings):
 # Two archives of the same class: identical plan + sensor table, later class
 # only overwrote the reading groups of two sensors (ids 2 and 7).
 pair=('课上第一次分组存档','课上第二次分组存档')
 if s.query(Trace).filter(Trace.name.in_(pair)).first():return
 base_readings=[dict(r) for r in readings]
 target_readings=[dict(r) for r in readings]
 for r in target_readings:
  if r['sensor_id'] in (2,7):r['value']=round(r['value']+12.5,1)
 base_ds=Dataset(name=pair[0],sensors=[dict(x) for x in sensors],readings=base_readings,description='复现试算基准：第一次课的采样存档')
 target_ds=Dataset(name=pair[1],sensors=[dict(x) for x in sensors],readings=target_readings,description='复现目标：第二次课的采样存档，仅传感器2/7整组采样有改动')
 s.add_all([base_ds,target_ds]);s.flush()
 plan=Plan(name='两次分组复核同一算子',dataset_id=base_ds.id,steps=DEFAULT_STEPS,note='复现试算固定使用原算子序列')
 s.add(plan);s.flush()
 for ds in (base_ds,target_ds):
  snap_ds={'id':ds.id,'name':ds.name,'description':ds.description,'sensors':ds.sensors,'readings':ds.readings}
  snap_plan={'id':plan.id,'name':plan.name,'dataset_id':plan.dataset_id,'steps':DEFAULT_STEPS,'note':plan.note}
  result=execute(snap_ds,DEFAULT_STEPS)
  s.add(Trace(name=pair[0] if ds is base_ds else pair[1],plan_id=plan.id,dataset_id=ds.id,status='completed',result=result,snapshot={'dataset':snap_ds,'plan':snap_plan}))
if __name__=='__main__':seed()
