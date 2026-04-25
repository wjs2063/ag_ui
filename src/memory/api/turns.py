"""L1: Raw Turn 저장/조회 API (MongoDB)"""
from fastapi import APIRouter, Request

from src.memory.core.schemas import TurnWriteRequest

router = APIRouter()


@router.post("/turns")
async def write_turns(req: TurnWriteRequest, request: Request):
    l1 = request.app.state.l1_store
    count = await l1.write_turns(req.user_id, req.turns)
    return {"status": "ok", "stored": count}


@router.get("/turns/{user_id}")
async def get_recent_turns(
    user_id: str, request: Request, limit: int = 20,
):
    l1 = request.app.state.l1_store
    turns = await l1.get_recent_turns(user_id, limit)
    return {"user_id": user_id, "turns": turns}


@router.get("/turns/{user_id}/unextracted")
async def get_unextracted_turns(user_id: str, request: Request):
    l1 = request.app.state.l1_store
    turns = await l1.get_unextracted_turns(user_id)
    return {"user_id": user_id, "count": len(turns), "turns": turns}
