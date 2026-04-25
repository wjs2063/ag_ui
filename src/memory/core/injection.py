from __future__ import annotations

from src.memory.core.schemas import (
    FieldCategory,
    InjectionTier,
    MemoryField,
)

# always inject 대상 카테고리
ALWAYS_INJECT_CATEGORIES = {
    FieldCategory.USER_PROFILE,
    FieldCategory.STABLE_PREFERENCE,
}

# intent → category 매핑
INTENT_CATEGORY_MAP: dict[str, set[FieldCategory]] = {
    "navigation": {
        FieldCategory.ROUTINE_PATTERN,
        FieldCategory.STABLE_PREFERENCE,
    },
    "recommendation": {
        FieldCategory.STABLE_PREFERENCE,
        FieldCategory.VOLATILE_PREFERENCE,
    },
    "scheduling": {
        FieldCategory.ROUTINE_PATTERN,
        FieldCategory.EVENT,
    },
    "social": {
        FieldCategory.RELATIONSHIP,
        FieldCategory.EVENT,
    },
}


def filter_by_tiers(
    fields: list[MemoryField],
    tiers: list[InjectionTier],
    intent: str | None,
) -> list[MemoryField]:
    result: list[MemoryField] = []
    seen_ids: set[str] = set()

    if InjectionTier.ALWAYS in tiers:
        for f in fields:
            if f.category in ALWAYS_INJECT_CATEGORIES:
                result.append(f)
                seen_ids.add(f.field_id)

    if InjectionTier.INTENT_MATCHED in tiers and intent:
        categories = INTENT_CATEGORY_MAP.get(intent, set())
        for f in fields:
            if f.field_id not in seen_ids and f.category in categories:
                result.append(f)
                seen_ids.add(f.field_id)

    return result
