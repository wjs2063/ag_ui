from __future__ import annotations

from src.memory.core.schemas import GraphEdge, MemoryField


def estimate_tokens(text: str) -> int:
    return len(text) // 3  # rough estimate, 한글 기준


def trim_to_budget(
    fields: list[MemoryField],
    edges: list[GraphEdge],
    budget: int,
) -> tuple[list[MemoryField], list[GraphEdge], int]:
    used = 0
    kept_fields: list[MemoryField] = []
    kept_edges: list[GraphEdge] = []

    # fields 우선 (confidence 높은 순)
    for f in sorted(fields, key=lambda x: x.confidence, reverse=True):
        cost = estimate_tokens(f"{f.key}: {f.value}")
        if used + cost > budget:
            break
        kept_fields.append(f)
        used += cost

    # 남은 budget으로 graph edges
    for e in sorted(edges, key=lambda x: x.confidence, reverse=True):
        cost = estimate_tokens(f"{e.subject} {e.predicate} {e.obj}")
        if used + cost > budget:
            break
        kept_edges.append(e)
        used += cost

    return kept_fields, kept_edges, used
