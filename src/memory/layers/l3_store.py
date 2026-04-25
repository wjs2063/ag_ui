"""L3: Graph Store — mem0 + Memgraph

mem0가 LLM으로 entity/relation을 자동 추출하고 Memgraph에 저장.
L2에서 추출된 structured data를 기반으로 graph를 구축.
"""
from __future__ import annotations

import logging
from typing import Any

from mem0 import Memory

logger = logging.getLogger(__name__)


def _build_config(
    memgraph_url: str,
    memgraph_username: str,
    memgraph_password: str,
) -> dict:
    return {
        "graph_store": {
            "provider": "memgraph",
            "config": {
                "url": memgraph_url,
                "username": memgraph_username,
                "password": memgraph_password,
            },
        },
        "version": "v1.1",
    }


class L3Store:
    def __init__(
        self,
        memgraph_url: str = "bolt://localhost:7687",
        memgraph_username: str = "memgraph",
        memgraph_password: str = "memgraph",
    ) -> None:
        config = _build_config(memgraph_url, memgraph_username, memgraph_password)
        self._mem0 = Memory.from_config(config_dict=config)
        logger.info("L3: mem0 + Memgraph initialized (%s)", memgraph_url)

    # ── Create ──

    async def add(
        self, user_id: str, data: str,
    ) -> dict[str, Any]:
        """텍스트에서 entity/relation을 추출하여 그래프에 저장.

        Args:
            user_id: 사용자 ID
            data: 추출 대상 텍스트 (L2 fields를 문장으로 변환한 것)
        """
        result = self._mem0.add(
            data, user_id=user_id,
        )
        logger.info("L3: added graph data for user %s", user_id)
        return result

    async def add_from_l2_fields(
        self, user_id: str, fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """L2에서 추출된 structured field들을 그래프에 반영."""
        sentences = []
        for f in fields:
            sentences.append(f"{f.get('key', '')}: {f.get('value', '')}")

        if not sentences:
            return {"added_entities": [], "deleted_entities": []}

        data = ". ".join(sentences)
        return await self.add(user_id, data)

    # ── Read ──

    async def search(
        self, user_id: str, query: str, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """그래프에서 query 관련 entity/relation 검색."""
        results = self._mem0.search(
            query, user_id=user_id, limit=limit,
        )
        return results if isinstance(results, list) else results.get("results", [])

    async def get_all(
        self, user_id: str, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """사용자의 모든 graph 관계 조회."""
        results = self._mem0.get_all(user_id=user_id, limit=limit)
        return results if isinstance(results, list) else results.get("results", [])

    # ── Update ──
    # mem0 add()가 자동으로 기존 entity와 모순 감지 후 update 처리함.
    # 명시적 update가 필요하면 delete + add 패턴 사용.

    async def update(
        self, user_id: str, old_data: str, new_data: str,
    ) -> dict[str, Any]:
        """기존 관계를 삭제하고 새 관계를 추가 (delete + add)."""
        await self.delete(user_id, old_data)
        return await self.add(user_id, new_data)

    # ── Delete ──

    async def delete(
        self, user_id: str, data: str,
    ) -> None:
        """텍스트에 해당하는 entity/relation 삭제."""
        self._mem0.delete(data, user_id=user_id)
        logger.info("L3: deleted graph data for user %s", user_id)

    async def delete_all(self, user_id: str) -> None:
        """사용자의 모든 graph 데이터 삭제."""
        self._mem0.delete_all(user_id=user_id)
        logger.info("L3: deleted all graph data for user %s", user_id)
