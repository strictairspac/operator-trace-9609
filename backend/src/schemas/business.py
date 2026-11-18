from pydantic import BaseModel,Field,model_validator,ConfigDict
from typing import Literal
from src.services.operators import validate_steps
class Login(BaseModel):
 email:str;password:str
class Sensor(BaseModel):
 model_config=ConfigDict(extra='forbid')
 sensor_id:int=Field(ge=1,le=100000)
 zone:str=Field(min_length=1,max_length=40)
 device_type:Literal['pump','motor','valve']
class Reading(BaseModel):
 model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
 sensor_id:int=Field(ge=1,le=100000)
 value:float=Field(ge=-1000000,le=1000000)
 recorded_at:str=Field(min_length=1,max_length=40)
class DatasetInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 description:str=Field(default='',max_length=500)
 sensors:list[Sensor]=Field(max_length=100)
 readings:list[Reading]=Field(max_length=2000)
class PlanInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 dataset_id:int
 steps:list[dict]
 note:str=Field(default='',max_length=500)
 @model_validator(mode='after')
 def validate(self):validate_steps(self.steps);return self
class TraceInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 plan_id:int
