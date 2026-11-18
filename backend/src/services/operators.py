"""A bounded teaching execution engine; this does not replace PostgreSQL execution."""
from collections import defaultdict
from decimal import Decimal
import time,json,hashlib,math
from src.constants.enums import OPERATORS
MAX_ROWS=10000
READING_FIELDS={'sensor_id','value','recorded_at'}
SENSOR_FIELDS={'sensor_id','zone','device_type'}
def validate_steps(steps):
 if not isinstance(steps,list) or not 1<=len(steps)<=6:raise ValueError('计划须包含1至6个算子')
 fields=set();grouped=False
 for i,step in enumerate(steps):
  if not isinstance(step,dict) or step.get('op') not in OPERATORS:raise ValueError('非法算子；仅允许scan/filter/hash_join/group')
  op=step['op']
  if i==0 and op!='scan':raise ValueError('第一步必须是scan')
  if op=='scan':
   if i!=0 or step!={'op':'scan','source':'readings'}:raise ValueError('scan只能在首步读取readings')
   fields=READING_FIELDS.copy()
  elif op=='filter':
   if set(step)!={'op','field','compare','value'} or not isinstance(step['field'],str) or step['field'] not in fields or step['compare'] not in ('eq','gte','lte'):raise ValueError('filter字段或比较方式无效')
   if step['compare']!='eq' and (step['field'] not in ('sensor_id','value','count','sum','avg') or not isinstance(step['value'],(int,float)) or not math.isfinite(step['value'])):raise ValueError('范围筛选只接受数值字段和有限数值')
   if not isinstance(step['value'],(str,int,float)) or isinstance(step['value'],bool) or (isinstance(step['value'],float) and not math.isfinite(step['value'])):raise ValueError('filter值只接受文本或数值')
  elif op=='hash_join':
   if grouped or not READING_FIELDS.issubset(fields) or step!={'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'}:raise ValueError('hash_join仅支持分组前readings与sensors按sensor_id内连接')
   if 'zone' in fields:raise ValueError('一个计划只允许一次连接')
   fields|=SENSOR_FIELDS
  elif op=='group':
   if set(step)!={'op','keys','measure','aggregate'} or grouped:raise ValueError('仅允许一次group，参数为keys/measure/aggregate')
   keys=step['keys']
   if not isinstance(keys,list) or not 1<=len(keys)<=2 or any(not isinstance(k,str) for k in keys) or len(set(keys))!=len(keys) or any(k not in fields for k in keys):raise ValueError('分组字段无效')
   if step['measure']!='value' or step['aggregate'] not in ('count','sum','avg'):raise ValueError('group仅允许value的count/sum/avg')
   fields=set(keys)|{step['aggregate']};grouped=True
 return steps

def checksum(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def execute(dataset,steps):
 validate_steps(steps);rows=[];trace=[];total_started=time.perf_counter();reads=0
 for step in steps:
  before=len(rows);started=time.perf_counter();detail={}
  if step['op']=='scan':
   rows=[dict(r) for r in dataset['readings']];reads+=len(rows);detail={'source':'readings','scanned_rows':len(rows)}
  elif step['op']=='filter':
   field,cmp,value=step['field'],step['compare'],step['value']
   def match(row):
    v=row[field]
    if cmp=='eq':return v==value
    if not isinstance(v,(int,float)):raise ValueError('范围比较遇到非数值')
    return v>=value if cmp=='gte' else v<=value
   reads+=len(rows);rows=[r for r in rows if match(r)];detail={'predicate':step,'removed_rows':before-len(rows)}
  elif step['op']=='hash_join':
   buckets=defaultdict(list)
   for sensor in dataset['sensors']:buckets[sensor['sensor_id']].append(sensor)
   joined=[];probes=0
   for row in rows:
    probes+=1
    for sensor in buckets.get(row['sensor_id'],[]):
     joined.append({**row,**sensor})
     if len(joined)>MAX_ROWS:raise ValueError('连接结果超过10000行，请缩小输入；未保存部分结果')
   reads+=len(rows)+len(dataset['sensors']);rows=joined;detail={'build_rows':len(dataset['sensors']),'hash_buckets':len(buckets),'probe_rows':probes,'semantics':'inner join; duplicate right keys retain multiplicity'}
  elif step['op']=='group':
   grouped=defaultdict(list);keys=step['keys'];agg=step['aggregate']
   for row in rows:grouped[tuple(row[k] for k in keys)].append(Decimal(str(row['value'])))
   reads+=len(rows);rows=[]
   for key,values in grouped.items():
    value=len(values) if agg=='count' else float(sum(values)) if agg=='sum' else float(sum(values)/len(values))
    rows.append({**dict(zip(keys,key)),agg:round(value,6) if isinstance(value,float) else value})
   rows.sort(key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False));detail={'groups':len(rows),'aggregate':agg,'accumulator':'decimal from source string; rounded 6 decimals'}
  trace.append({'op':step['op'],'input_rows':before,'output_rows':len(rows),'duration_ms':round((time.perf_counter()-started)*1000,4),'detail':detail,'checksum':checksum(rows),'preview':rows[:5]})
 return {'operators':trace,'output':rows,'output_rows':len(rows),'checksum':checksum(rows),'row_visits':reads,'duration_ms':round((time.perf_counter()-total_started)*1000,4),'limits':{'max_readings':2000,'max_sensors':100,'max_join_rows':10000,'max_stages':6},'model':'Python teaching scan/filter/hash join/group engine; PostgreSQL persists business metadata only'}
