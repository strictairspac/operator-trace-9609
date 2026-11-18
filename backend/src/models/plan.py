from sqlalchemy import Column,Integer,String,JSON,ForeignKey
from src.config.database import Base
class Plan(Base):
 __tablename__='plans'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 dataset_id=Column(Integer,ForeignKey('datasets.id'),nullable=False)
 steps=Column(JSON,nullable=False)
 note=Column(String(500),nullable=False,default='')
