from sqlalchemy import Column,Integer,String,JSON
from src.config.database import Base
class Dataset(Base):
 __tablename__='datasets'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 description=Column(String(500),nullable=False,default='')
 sensors=Column(JSON,nullable=False)
 readings=Column(JSON,nullable=False)
