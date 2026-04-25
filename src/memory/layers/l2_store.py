"""L2: Structured Personal Data Store (POC: in-memory, 실제: PostgreSQL)"""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime

from langchain_openai import ChatOpenAI

from src.memory.core.schemas import (
    FieldCategory,
    FieldStats,
    MemoryField,
    Mutability,
)

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """\
아래 사용자 대화에서 개인화에 유용한 정보를 추출해줘.
반드시 JSON 배열로만 응답하고, 다른 텍스트는 포함하지 마.

각 항목 형식:
{{
  "key": "필드명 (영문 snake_case)",
  "value": "추출된 값",
  "category": "user_profile | stable_preference | volatile_preference | routine_pattern | relationship | event",
  "mutability": "immutable | slow_change | volatile",
  "confidence": 0.0~1.0
}}

추출 기준:
- user_profile: 이름, 나이, 직업, 거주지 등
- stable_preference: 음식, 음악, 온도, 취미 등 잘 안 바뀌는 선호
- volatile_preference: 요즘 관심사, 최근 듣는 노래 등
- routine_pattern: 출퇴근, 주말 패턴, 식사 시간 등
- relationship: 자주 언급하는 사람 (가족, 동료 등)
- event: 예정된 약속, 기념일 등

추출할 정보가 없으면 빈 배열 []을 반환해.

사용자 대화:
{turns_text}
"""


class L2Store:
    def __init__(self) -> None:
        self._fields: dict[str, dict[str, MemoryField]] = defaultdict(dict)
        self._stats: dict[str, FieldStats] = {}
        self._llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    async def upsert_field(self, field: MemoryField) -> MemoryField:
        user_fields = self._fields[field.user_id]

        # 같은 key가 있으면 update
        existing = next(
            (f for f in user_fields.values() if f.key == field.key),
            None,
        )
        if existing:
            existing.value = field.value
            existing.confidence = field.confidence
            existing.source_turn_id = field.source_turn_id
            existing.updated_at = datetime.utcnow()
            logger.info("L2: updated field %s for user %s", field.key, field.user_id)
            return existing

        if not field.field_id:
            field.field_id = uuid.uuid4().hex[:12]
        user_fields[field.field_id] = field
        self._stats[field.field_id] = FieldStats(field_id=field.field_id)
        logger.info("L2: created field %s for user %s", field.key, field.user_id)
        return field

    async def get_fields(
        self, user_id: str,
        categories: set[FieldCategory] | None = None,
    ) -> list[MemoryField]:
        fields = list(self._fields[user_id].values())
        if categories:
            fields = [f for f in fields if f.category in categories]
        return fields

    async def get_stats(self, field_id: str) -> FieldStats | None:
        return self._stats.get(field_id)

    async def increment_stat(
        self, field_id: str, stat_name: str, count: int = 1,
    ) -> None:
        stats = self._stats.get(field_id)
        if stats and hasattr(stats, stat_name):
            current = getattr(stats, stat_name)
            setattr(stats, stat_name, current + count)

    async def extract_from_turns(
        self, user_id: str, turns_text: str,
    ) -> list[MemoryField]:
        """LLM 기반 개인화 데이터 추출."""
        prompt = EXTRACT_PROMPT.format(turns_text=turns_text)

        try:
            response = await self._llm.ainvoke(prompt)
            raw = response.content.strip()
            # markdown code block 제거
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            items = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.exception("L2: LLM extraction failed: %s", e)
            return []

        extracted: list[MemoryField] = []
        for item in items:
            try:
                field = MemoryField(
                    field_id=uuid.uuid4().hex[:12],
                    user_id=user_id,
                    category=FieldCategory(item["category"]),
                    key=item["key"],
                    value=item["value"],
                    mutability=Mutability(item.get("mutability", "slow_change")),
                    confidence=float(item.get("confidence", 0.8)),
                )
                result = await self.upsert_field(field)
                extracted.append(result)
            except (KeyError, ValueError) as e:
                logger.warning("L2: skipping invalid item: %s", e)

        logger.info(
            "L2: extracted %d fields for user %s", len(extracted), user_id,
        )
        return extracted
