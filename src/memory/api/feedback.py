"""피드백 API — 메모리 유용성 지표 수집"""
from fastapi import APIRouter, Request

from src.memory.core.schemas import FeedbackRequest

router = APIRouter()


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request):
    l2 = request.app.state.l2_store

    for field_id in req.injected_field_ids:
        await l2.increment_stat(field_id, "used_in_response")
        if req.is_correction:
            await l2.increment_stat(field_id, "correction_count")

    return {
        "status": "ok",
        "processed": len(req.injected_field_ids),
        "is_correction": req.is_correction,
    }


@router.get("/stats/{user_id}")
async def get_memory_stats(user_id: str, request: Request):
    l2 = request.app.state.l2_store
    fields = await l2.get_fields(user_id)

    stats = []
    for f in fields:
        s = await l2.get_stats(f.field_id)
        if s:
            stats.append({
                "field_id": f.field_id,
                "key": f.key,
                "value": f.value,
                **s.model_dump(),
                "acceptance_rate": s.acceptance_rate,
            })

    return {"user_id": user_id, "stats": stats}
