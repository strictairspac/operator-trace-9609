from fastapi import HTTPException
from src.config.database import Session
from src.models.dataset import Dataset
from src.utils.serialization import record

def list_items():
 with Session() as s:return [record(r) for r in s.query(Dataset).order_by(Dataset.id.desc()).all()]
def save(data,item_id=None):
 with Session() as s:
  row=s.get(Dataset,item_id) if item_id else Dataset()
  if not row:raise HTTPException(404,'未找到记录')
  for k,v in data.model_dump().items():setattr(row,k,v)
  s.add(row);s.commit();s.refresh(row);return record(row)
