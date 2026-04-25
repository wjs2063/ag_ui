"""L3: Memgraph CRUD API"""
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class GraphAddRequest(BaseModel):
    user_id: str
    data: str  # 자연어 텍스트 (entity/relation 자동 추출)


class GraphSearchRequest(BaseModel):
    user_id: str
    query: str
    limit: int = 5


class GraphUpdateRequest(BaseModel):
    user_id: str
    old_data: str
    new_data: str


class GraphDeleteRequest(BaseModel):
    user_id: str
    data: str


# ── Create ──

@router.post("/graph/add")
async def add_to_graph(req: GraphAddRequest, request: Request):
    l3 = request.app.state.l3_store
    result = await l3.add(req.user_id, req.data)
    return {"status": "ok", "result": result}


# ── Read ──

@router.post("/graph/search")
async def search_graph(req: GraphSearchRequest, request: Request):
    l3 = request.app.state.l3_store
    results = await l3.search(req.user_id, req.query, req.limit)
    return {"user_id": req.user_id, "results": results}


@router.get("/graph/{user_id}/all")
async def get_all_relations(
    user_id: str, request: Request, limit: int = 100,
):
    l3 = request.app.state.l3_store
    results = await l3.get_all(user_id, limit)
    return {"user_id": user_id, "results": results}


# ── Update ──

@router.put("/graph/update")
async def update_graph(req: GraphUpdateRequest, request: Request):
    l3 = request.app.state.l3_store
    result = await l3.update(req.user_id, req.old_data, req.new_data)
    return {"status": "ok", "result": result}


# ── Delete ──

@router.post("/graph/delete")
async def delete_from_graph(req: GraphDeleteRequest, request: Request):
    l3 = request.app.state.l3_store
    await l3.delete(req.user_id, req.data)
    return {"status": "ok"}


@router.delete("/graph/{user_id}")
async def delete_all_graph(user_id: str, request: Request):
    l3 = request.app.state.l3_store
    await l3.delete_all(user_id)
    return {"status": "ok"}
