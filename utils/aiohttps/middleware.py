"""
FastAPI 미들웨어 — 요청 단위 request_id 세팅 + 외부 API trace 로깅.

사용법:
    from ai_poc.utils.aiohttps.middleware import TraceMiddleware

    app = FastAPI()
    app.add_middleware(TraceMiddleware)
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .request_context import init_request_context, get_current_trace_records, request_id_var

logger = logging.getLogger("api.trace")


class TraceMiddleware(BaseHTTPMiddleware):
    """
    각 FastAPI 요청마다:
    1. request_id를 생성하고 ContextVar에 세팅
    2. trace_records 리스트를 초기화
    3. 요청 처리 중 aiohttp trace 콜백이 타이밍 데이터를 수집
    4. 응답/예외 시 수집된 trace_records를 로깅
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = init_request_context()

        request_start = time.perf_counter()
        logger.info(f"[{request_id}] → {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - request_start) * 1000, 4)
            self._log_trace_summary(request_id, request, elapsed_ms, error=str(exc))
            raise

        elapsed_ms = round((time.perf_counter() - request_start) * 1000, 4)
        self._log_trace_summary(request_id, request, elapsed_ms, status=response.status_code)

        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _log_trace_summary(
        request_id: str,
        request: Request,
        total_elapsed_ms: float,
        status: int | None = None,
        error: str | None = None,
    ) -> None:
        records = get_current_trace_records()

        summary = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "total_elapsed_ms": total_elapsed_ms,
            "status": status,
            "error": error,
            "external_calls": [r.to_dict() for r in records],
        }

        if error:
            logger.error(f"[{request_id}] ✗ {request.method} {request.url.path} ({total_elapsed_ms}ms) error={error}")
        else:
            logger.info(f"[{request_id}] ← {request.method} {request.url.path} → {status} ({total_elapsed_ms}ms)")

        if records:
            logger.info(f"[{request_id}] external_calls={summary['external_calls']}")
