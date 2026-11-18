from fastapi import HTTPException
from src.config.database import Session
from src.models.plan import Plan
from src.utils.serialization import record
from src.models.dataset import Dataset

def list_items():
 with Session() as s:return [record(r) for r in s.query(Plan).order_by(Plan.id.desc()).all()]
def save(data,item_id=None):
 with Session() as s:
  if not s.get(Dataset,data.dataset_id):raise HTTPException(404,'未找到数据集')
  row=s.get(Plan,item_id) if item_id else Plan()
  if not row:raise HTTPException(404,'未找到记录')
  for k,v in data.model_dump().items():setattr(row,k,v)
  s.add(row);s.commit();s.refresh(row);return record(row)
