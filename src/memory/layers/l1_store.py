"""L1: Raw Turn Store — MongoDB (motor async driver)"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from src.memory.core.schemas import Turn

logger = logging.getLogger(__name__)


class L1Store:
    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017",
        db_name: str = "memory",
    ) -> None:
        self._client = AsyncIOMotorClient(mongo_uri)
        self._db = self._client[db_name]
        self._col: AsyncIOMotorCollection = self._db["turns"]

    async def ensure_indexes(self) -> None:
        await self._col.create_index("user_id")
        await self._col.create_index([("user_id", 1), ("extracted", 1)])
        await self._col.create_index("turn_id", unique=True)

    async def write_turns(
        self, user_id: str, turns: list[Turn],
    ) -> int:
        if not turns:
            return 0
        docs = [t.model_dump() for t in turns]
        for d in docs:
            d["extracted"] = False
        result = await self._col.insert_many(docs)
        logger.info(
            "L1: stored %d turns for user %s", len(result.inserted_ids), user_id,
        )
        return len(result.inserted_ids)

    async def get_recent_turns(
        self, user_id: str, limit: int = 20,
    ) -> list[Turn]:
        cursor = self._col.find(
            {"user_id": user_id},
        ).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        docs.reverse()  # 오래된 순
        return [Turn(**d) for d in docs]

    async def get_unextracted_turns(
        self, user_id: str,
    ) -> list[Turn]:
        """L2 batch 처리되지 않은 turn 조회."""
        cursor = self._col.find(
            {"user_id": user_id, "extracted": False},
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=1000)
        return [Turn(**d) for d in docs]

    async def mark_extracted(
        self, turn_ids: list[str],
    ) -> int:
        """처리 완료된 turn의 extracted flag를 True로 변경."""
        if not turn_ids:
            return 0
        result = await self._col.update_many(
            {"turn_id": {"$in": turn_ids}},
            {"$set": {"extracted": True}},
        )
        logger.info("L1: marked %d turns as extracted", result.modified_count)
        return result.modified_count

    async def get_context_turns(
        self, user_id: str, before_turn_id: str, limit: int = 10,
    ) -> list[Turn]:
        """특정 turn 이전의 대화 맥락 조회 (이미 추출된 것 포함)."""
        ref = await self._col.find_one({"turn_id": before_turn_id})
        if not ref:
            return await self.get_recent_turns(user_id, limit)

        cursor = self._col.find({
            "user_id": user_id,
            "created_at": {"$lt": ref["created_at"]},
        }).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        docs.reverse()
        return [Turn(**d) for d in docs]

    async def get_turns_by_ids(
        self, user_id: str, turn_ids: list[str],
    ) -> list[Turn]:
        cursor = self._col.find({
            "user_id": user_id,
            "turn_id": {"$in": turn_ids},
        }).sort("created_at", 1)
        docs = await cursor.to_list(length=len(turn_ids))
        return [Turn(**d) for d in docs]
