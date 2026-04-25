"""통합 조회 API — L2 structured + L3 memgraph를 token budget 내로 반환"""
from typing import Any

from fastapi import APIRouter, Request

from src.memory.core.injection import filter_by_tiers
from src.memory.core.schemas import (
    InjectionTier,
    MemoryField,
    RetrieveRequest,
)
from src.memory.core.token_budget import estimate_tokens

router = APIRouter()


@router.post("/retrieve")
async def retrieve_memory(req: RetrieveRequest, request: Request):
    l2 = request.app.state.l2_store
    l3 = request.app.state.l3_store

    budget = req.token_budget
    used = 0

    # L2: structured fields
    all_fields = await l2.get_fields(req.user_id)
    filtered = filter_by_tiers(all_fields, req.tiers, req.intent)

    kept_fields: list[MemoryField] = []
    for f in sorted(filtered, key=lambda x: x.confidence, reverse=True):
        cost = estimate_tokens(f"{f.key}: {f.value}")
        if used + cost > budget:
            break
        kept_fields.append(f)
        used += cost

    for f in kept_fields:
        await l2.increment_stat(f.field_id, "injected_count")

    # L3: memgraph search (graph_enriched tier 요청 시)
    # memgraph 응답: [{"source": ..., "relationship": ..., "destination": ...}]
    graph_relations: list[dict[str, Any]] = []
    if InjectionTier.GRAPH_ENRICHED in req.tiers and req.intent:
        results = await l3.search(req.user_id, req.intent, limit=10)
        for r in results:
            text = f"{r.get('source', '')} {r.get('relationship', '')} {r.get('destination', r.get('target', ''))}"
            cost = estimate_tokens(text)
            if used + cost > budget:
                break
            graph_relations.append(r)
            used += cost

    return {
        "user_id": req.user_id,
        "fields": kept_fields,
        "graph_relations": graph_relations,
        "token_count": used,
    }
