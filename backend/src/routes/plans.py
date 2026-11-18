from fastapi import APIRouter,Depends
from src.middlewares.auth import current,writer
from src.schemas.business import PlanInput
from src.services import plans
from src.controllers.business import save_plan
router=APIRouter()
@router.get('/plans')
def listing(u=Depends(current)):return plans.list_items()
@router.post('/plans')
def create(data:PlanInput,u=Depends(writer)):return save_plan(data,u)
@router.put('/plans/{item_id}')
def update(item_id:int,data:PlanInput,u=Depends(writer)):return save_plan(data,u,item_id)
