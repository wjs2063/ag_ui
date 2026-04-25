from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── L1: Raw Turn ──


class Turn(BaseModel):
    turn_id: str
    user_id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    extracted: bool = False  # L2 batch 처리 완료 여부


# ── L2: Structured Personal Data ──


class FieldCategory(str, Enum):
    USER_PROFILE = "user_profile"
    STABLE_PREFERENCE = "stable_preference"
    VOLATILE_PREFERENCE = "volatile_preference"
    ROUTINE_PATTERN = "routine_pattern"
    RELATIONSHIP = "relationship"
    EVENT = "event"


class Mutability(str, Enum):
    IMMUTABLE = "immutable"      # 이름, 생년월일
    SLOW_CHANGE = "slow_change"  # 직업, 주소
    VOLATILE = "volatile"        # 최근 관심사, 진행중 일정


class MemoryField(BaseModel):
    field_id: str
    user_id: str
    category: FieldCategory
    key: str                     # "preferred_name", "coffee_preference" 등
    value: Any
    mutability: Mutability = Mutability.SLOW_CHANGE
    confidence: float = 1.0
    source_turn_id: str | None = None
    consumer_agents: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Memory Field Stats (유용성 지표) ──


class FieldStats(BaseModel):
    field_id: str
    extracted_count: int = 0
    injected_count: int = 0
    used_in_response: int = 0
    correction_count: int = 0

    @property
    def acceptance_rate(self) -> float:
        if self.injected_count == 0:
            return 0.0
        return (self.injected_count - self.correction_count) / self.injected_count


# ── API Request/Response ──


class InjectionTier(str, Enum):
    ALWAYS = "always"
    INTENT_MATCHED = "intent_matched"
    GRAPH_ENRICHED = "graph_enriched"


class RetrieveRequest(BaseModel):
    user_id: str
    intent: str | None = None
    tiers: list[InjectionTier] = Field(
        default=[InjectionTier.ALWAYS, InjectionTier.INTENT_MATCHED],
    )
    token_budget: int = 400


class TurnWriteRequest(BaseModel):
    user_id: str
    turns: list[Turn]


class ExtractRequest(BaseModel):
    user_id: str
    context_window: int = 10  # 맥락용 기존 대화 수


class FeedbackRequest(BaseModel):
    user_id: str
    injected_field_ids: list[str]
    is_correction: bool = False
    correction_detail: str | None = None
