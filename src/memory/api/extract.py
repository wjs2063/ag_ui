"""L2 + L3 Batch Extraction API

흐름:
1. L1에서 extracted=False인 turn들을 조회
2. 맥락을 위해 이전 대화도 함께 가져옴
3. L2: LLM으로 structured field 추출
4. L3: L2 결과를 memgraph에 반영
5. 처리 완료된 L1 turn에 extracted=True 마킹
"""
from fastapi import APIRouter, Request

from src.memory.core.schemas import ExtractRequest

router = APIRouter()


@router.post("/extract")
async def extract_memory(req: ExtractRequest, request: Request):
    l1 = request.app.state.l1_store
    l2 = request.app.state.l2_store
    l3 = request.app.state.l3_store

    # 1. 미처리 turn 조회
    unextracted = await l1.get_unextracted_turns(req.user_id)
    if not unextracted:
        return {"status": "ok", "processed": 0, "l2_extracted": 0, "l3_result": None}

    # 2. 맥락용 기존 대화 가져오기
    first_turn_id = unextracted[0].turn_id
    context_turns = await l1.get_context_turns(
        req.user_id, first_turn_id, limit=req.context_window,
    )

    # 맥락 + 미처리 turn 합치기
    context_text = ". ".join(t.content for t in context_turns)
    new_text = ". ".join(
        t.content for t in unextracted if t.role == "user"
    )
    turns_text = f"[이전 맥락]\n{context_text}\n\n[새 대화]\n{new_text}" if context_text else new_text

    # 3. L2: LLM 기반 structured field 추출
    fields = await l2.extract_from_turns(req.user_id, turns_text)

    # 4. L3: L2 결과를 memgraph에 반영
    graph_result = None
    if fields:
        field_dicts = [{"key": f.key, "value": f.value} for f in fields]
        graph_result = await l3.add_from_l2_fields(req.user_id, field_dicts)

    # 5. 처리 완료 마킹
    turn_ids = [t.turn_id for t in unextracted]
    await l1.mark_extracted(turn_ids)

    return {
        "status": "ok",
        "processed": len(unextracted),
        "l2_extracted": len(fields),
        "l2_fields": fields,
        "l3_result": graph_result,
    }
