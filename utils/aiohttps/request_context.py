"""
요청 단위 ContextVar 정의.

FastAPI 미들웨어에서 세팅하고, aiohttp trace 콜백에서 읽어 타이밍 데이터를 수집한다.

구조:
    request_id_var  ← 요청 식별자 (UUID)
    trace_records_var ← 외부 API 호출별 타이밍 기록 리스트

trace_records 에 쌓이는 단건 구조 예시:
    {
        "method": "GET",
        "url": "https://api.example.com/data",
        "pool": {"start": 1.200, "end": 1.234, "elapsed_ms": 34.0},
        "dns":  {"start": 1.234, "end": 1.240, "elapsed_ms": 6.0},
        "tcp":  {"start": 1.240, "end": 1.280, "elapsed_ms": 40.0},
        "request": {"start": 1.200, "end": 1.350, "elapsed_ms": 150.0},
        "status": 200,
        "error": None,
    }
"""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

SEOUL_TZ = ZoneInfo("Asia/Seoul")


def _now_seoul() -> str:
    """현재 서울 시간을 ISO 8601 형식으로 반환. (e.g. 2026-04-25T21:44:12.395+09:00)"""
    return datetime.now(SEOUL_TZ).isoformat(timespec="milliseconds")

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


@dataclass
class PhaseTimer:
    """단일 구간(DNS, TCP, Request) 타이밍"""
    start: str = ""
    end: str = ""
    elapsed_ms: float = 0.0
    status: str = "idle"  # idle → running → completed / timeout
    _start_perf: float = field(default=0.0, repr=False)

    def mark_start(self) -> None:
        self._start_perf = time.perf_counter()
        self.start = _now_seoul()
        self.status = "running"

    def mark_end(self) -> None:
        self.end = _now_seoul()
        self.elapsed_ms = round((time.perf_counter() - self._start_perf) * 1000, 4)
        self.status = "completed"

    def mark_timeout(self) -> None:
        """start만 호출되고 end가 안 된 구간을 타임아웃으로 마감."""
        self.end = _now_seoul()
        self.elapsed_ms = round((time.perf_counter() - self._start_perf) * 1000, 4)
        self.status = "timeout"

    def reset(self) -> None:
        """실제로 실행되지 않은 구간을 idle로 되돌린다."""
        self.start = ""
        self.end = ""
        self.elapsed_ms = 0.0
        self.status = "idle"
        self._start_perf = 0.0

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "elapsed_ms": self.elapsed_ms, "status": self.status}


@dataclass
class TraceRecord:
    """외부 API 호출 1건에 대한 전체 타이밍 기록"""
    method: str = ""
    url: str = ""
    pool: PhaseTimer = field(default_factory=PhaseTimer)
    dns: PhaseTimer = field(default_factory=PhaseTimer)
    tcp: PhaseTimer = field(default_factory=PhaseTimer)
    request: PhaseTimer = field(default_factory=PhaseTimer)
    resolved_ips: list[str] = field(default_factory=list)
    status: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "url": self.url,
            "pool": self.pool.to_dict(),
            "dns": self.dns.to_dict(),
            "tcp": self.tcp.to_dict(),
            "request": self.request.to_dict(),
            "resolved_ips": self.resolved_ips,
            "status": self.status,
            "error": self.error,
        }


trace_records_var: ContextVar[list[TraceRecord]] = ContextVar("trace_records", default=[])


def init_request_context() -> str:
    """미들웨어에서 호출. request_id 생성 + trace_records 초기화."""
    rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    trace_records_var.set([])
    return rid


def get_current_trace_records() -> list[TraceRecord]:
    return trace_records_var.get()
