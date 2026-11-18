from fastapi import APIRouter, Depends
from src.middlewares.auth import current, writer
from src.schemas.business import ReplayInput, ReplayPrecheck
from src.services import replay
from src.controllers.business import start_replay, precheck_replay, resume_replay
router = APIRouter()


@router.get('/replays')
def listing(u=Depends(current)):
	return replay.list_items()


@router.post('/replays/precheck')
def precheck(data: ReplayPrecheck, u=Depends(writer)):
	return precheck_replay(data, u)


@router.post('/replays')
def create(data: ReplayInput, u=Depends(writer)):
	return start_replay(data, u)


@router.get('/replays/{item_id}')
def detail(item_id: int, u=Depends(current)):
	return replay.detail(item_id)


@router.post('/replays/{item_id}/resume')
def resume(item_id: int, u=Depends(writer)):
	return resume_replay(item_id, u)
