"""
aiohttp TraceConfig — ContextVar + trace_request_ctx 기반 타이밍 수집.

각 외부 API 호출마다 고유한 TraceRequestContext(ctx)가 생성되어,
asyncio.gather() 병렬 호출에서도 콜백이 정확한 TraceRecord에 기록된다.
"""
import logging
import socket
from typing import Any, List
from aiohttp import (
    TraceConfig,
    TraceRequestStartParams,
    TraceRequestEndParams,
    TraceConnectionCreateStartParams,
    TraceConnectionCreateEndParams,
    TraceConnectionQueuedStartParams,
    TraceConnectionQueuedEndParams,
    TraceDnsResolveHostStartParams,
    TraceDnsResolveHostEndParams,
    TraceRequestExceptionParams,
    ClientSession,
)
from aiohttp.resolver import DefaultResolver, ResolveResult
from contextvars import ContextVar
from .request_context import (
    request_id_var,
    trace_records_var,
    TraceRecord,
)

# DNS 해석 결과를 콜백에 전달하기 위한 ContextVar
# DefaultResolver.resolve() → 결과 저장 → on_dns_resolvehost_end 콜백에서 읽기
_last_dns_result_var: ContextVar[list[str]] = ContextVar("_last_dns_result", default=[])

logger = logging.getLogger("aiohttp.trace")


class TracingResolver(DefaultResolver):
    """
    DefaultResolver를 래핑하여 DNS 해석 결과 IP를 ContextVar에 저장한다.

    aiohttp 내부 흐름:
        resolver.resolve(host, port)  ← 여기서 IP 확보 & ContextVar에 저장
        → send_dns_resolvehost_end()  ← 콜백에서 ContextVar 읽어 TraceRecord에 기록

    resolve() 결과는 aiohttp ResolveResult 리스트:
        [{"hostname": "httpbin.org", "host": "3.228.76.52", "port": 443, ...}, ...]
        - hostname: 원래 도메인명
        - host: 해석된 IP 주소 (getaddrinfo → libc → OS DNS 서버 → 최종 목적지 IP)
    """

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> List[ResolveResult]:
        results = await super().resolve(host, port, family)
        ips = [r["host"] for r in results]
        _last_dns_result_var.set(ips)
        return results


class TraceRequestContext:
    """
    aiohttp가 외부 API 호출 1건마다 생성하는 ctx 객체.
    on_request_start에서 TraceRecord를 할당하면,
    이후 모든 콜백(DNS, TCP, end, exception)에서 동일한 record를 참조한다.
    → asyncio.gather() 병렬 호출에서도 안전.

    aiohttp는 팩토리를 trace_request_ctx= 키워드 인자로 호출하므로 __init__에서 받아야 한다.
    """

    def __init__(self, trace_request_ctx: object = None) -> None:
        self.trace_request_ctx = trace_request_ctx
        self.record = TraceRecord()


def create_trace_config() -> TraceConfig:
    """
    aiohttp TraceConfig를 생성하고, 요청 라이프사이클의 주요 시점에 타이밍 수집 콜백을 등록한다.

    trace_config_ctx_factory=TraceRequestContext
      → 외부 API 호출마다 새 TraceRequestContext가 생성되어 ctx로 전달됨
      → 병렬 호출 시에도 각 콜백이 자신의 TraceRecord에만 기록

    요청 라이프사이클 순서:
        on_request_start          ← 요청 진입, ctx.record에 TraceRecord 할당
        │
        ├─ on_connection_queued_start/end (풀 한도 초과 시 슬롯 대기)
        ├─ on_dns_resolvehost_start/end   (DNS resolve 타이밍)
        ├─ on_connection_create_start/end (TCP + TLS 타이밍)
        │
        ├─ on_request_end                 (정상 완료, status 기록)
        └─ on_request_exception           (예외 발생, error 기록)
    """
    trace_config = TraceConfig(trace_config_ctx_factory=TraceRequestContext)

    # ──────────────────────────────────────────────────────────────
    # HTTP 요청 시작 — ctx.record에 TraceRecord 할당
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_request_start.append
    async def on_request_start(
        session: ClientSession, ctx: TraceRequestContext, params: TraceRequestStartParams
    ) -> None:
        """
        HTTP 요청이 시작될 때 호출.
        ctx.record에 새 TraceRecord를 할당하고, trace_records 리스트에 append한다.

        - params.method:  HTTP 메서드
        - params.url:     요청 URL (yarl.URL)
        - params.headers: 요청 헤더
        """
        rid = request_id_var.get()
        record = TraceRecord(method=params.method, url=str(params.url))
        record.request.mark_start()
        ctx.record = record
        trace_records_var.get().append(record)
        logger.info(f"[{rid}] [REQ START] {params.method} {params.url}")

    # ──────────────────────────────────────────────────────────────
    # Connection Pool 대기
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_connection_queued_start.append
    async def on_conn_queued_start(
        session: ClientSession, ctx: TraceRequestContext, params: TraceConnectionQueuedStartParams
    ) -> None:
        """
        Connector 풀(limit / limit_per_host)이 가득 차서 슬롯을 기다리기 시작.
        ctx.record.pool 타이머를 시작한다.

        이 콜백은 풀이 포화 상태일 때만 호출된다. 한도 내에서 즉시 슬롯을 잡으면
        호출되지 않으므로, pool.status == "idle"이면 대기 없이 진행된 것.
        """
        rid = request_id_var.get()
        ctx.record.pool.mark_start()
        logger.debug(f"[{rid}] [POOL] waiting for connection slot")

    @trace_config.on_connection_queued_end.append
    async def on_conn_queued_end(
        session: ClientSession, ctx: TraceRequestContext, params: TraceConnectionQueuedEndParams
    ) -> None:
        """
        풀에 슬롯이 생겨 대기 종료. ctx.record.pool 타이머를 종료한다.

        start ~ end = 풀 대기 소요 시간.
        이후 흐름: 재사용 가능한 keep-alive 커넥션이 있으면 바로 요청 진행,
        없으면 on_connection_create_start로 새 연결 생성.
        """
        rid = request_id_var.get()
        ctx.record.pool.mark_end()
        logger.debug(f"[{rid}] [POOL] slot acquired ({ctx.record.pool.elapsed_ms}ms)")

    # ──────────────────────────────────────────────────────────────
    # DNS 해석
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_dns_resolvehost_start.append
    async def on_dns_start(
        session: ClientSession, ctx: TraceRequestContext, params: TraceDnsResolveHostStartParams
    ) -> None:
        """
        DNS 이름 해석 시작. ctx.record.dns 타이머를 시작한다.

        - params.host: 해석 대상 호스트명

        관련 TCPConnector 설정:
        - use_dns_cache=True → 캐시 히트 시 이 콜백 미호출 (on_dns_cache_hit 대신)
        - ttl_dns_cache      → 캐시 TTL. 만료 후 재요청 시 다시 호출됨
        """
        rid = request_id_var.get()
        ctx.record.dns.mark_start()
        logger.debug(f"[{rid}] [DNS] resolving {params.host}")

    @trace_config.on_dns_resolvehost_end.append
    async def on_dns_end(
        session: ClientSession, ctx: TraceRequestContext, params: TraceDnsResolveHostEndParams
    ) -> None:
        """
        DNS 이름 해석 완료. ctx.record.dns 타이머를 종료하고, 해석된 IP를 기록한다.

        - params.host: 해석 완료된 호스트명

        TracingResolver가 resolve() 결과를 _last_dns_result_var에 저장해두고,
        이 콜백에서 읽어 ctx.record.resolved_ips에 기록한다.

        start ~ end = 실제 DNS resolve 소요 시간.
        """
        rid = request_id_var.get()
        ctx.record.dns.mark_end()
        ctx.record.resolved_ips = _last_dns_result_var.get()
        logger.debug(
            f"[{rid}] [DNS] resolved  {params.host} → {ctx.record.resolved_ips} "
            f"({ctx.record.dns.elapsed_ms}ms)"
        )

    # ──────────────────────────────────────────────────────────────
    # TCP 연결
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_connection_create_start.append
    async def on_conn_start(
        session: ClientSession, ctx: TraceRequestContext, params: TraceConnectionCreateStartParams
    ) -> None:
        """
        새 TCP 소켓(+TLS) 연결 생성 시작. ctx.record.tcp 타이머를 시작한다.

        관련 TCPConnector 설정:
        - limit / limit_per_host → 한도 내에서만 새 연결 → 이 콜백 호출
        - keepalive_timeout      → keep-alive 재사용 시 이 콜백 미호출
        - force_close=True       → 매 요청마다 새 연결 → 항상 호출
        """
        rid = request_id_var.get()
        ctx.record.tcp.mark_start()
        logger.debug(f"[{rid}] [CONN] creating connection")

    @trace_config.on_connection_create_end.append
    async def on_conn_end(
        session: ClientSession, ctx: TraceRequestContext, params: TraceConnectionCreateEndParams
    ) -> None:
        """
        TCP 소켓(+TLS) 연결 생성 완료. ctx.record.tcp 타이머를 종료한다.

        start ~ end = TCP 연결 + TLS 핸드셰이크 소요 시간.
        """
        rid = request_id_var.get()
        ctx.record.tcp.mark_end()
        logger.debug(f"[{rid}] [CONN] connection created ({ctx.record.tcp.elapsed_ms}ms)")

    # ──────────────────────────────────────────────────────────────
    # HTTP 요청 완료
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_request_end.append
    async def on_request_end(
        session: ClientSession, ctx: TraceRequestContext, params: TraceRequestEndParams
    ) -> None:
        """
        HTTP 응답 수신 완료. ctx.record.request 타이머를 종료하고 status를 기록한다.

        - params.response: aiohttp.ClientResponse (status, headers 등)

        주의: raise_for_status() 이전에 호출됨.
        4xx/5xx여도 응답 수신 성공이면 이 콜백이 호출된다.
        """
        rid = request_id_var.get()
        record = ctx.record
        record.request.mark_end()
        record.status = params.response.status
        logger.info(
            f"[{rid}] [REQ END] {params.method} {params.url} → {params.response.status} "
            f"(total={record.request.elapsed_ms}ms, pool={record.pool.elapsed_ms}ms, "
            f"dns={record.dns.elapsed_ms}ms, tcp={record.tcp.elapsed_ms}ms)"
        )

    # ──────────────────────────────────────────────────────────────
    # 요청 예외
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_request_exception.append
    async def on_request_exception(
        session: ClientSession, ctx: TraceRequestContext, params: TraceRequestExceptionParams
    ) -> None:
        """
        네트워크 레벨 예외 발생. ctx.record.request 타이머를 종료하고 error를 기록한다.

        - params.exception: 발생한 예외 (ConnectionError, TimeoutError 등)

        raise_for_status()에 의한 ClientResponseError는 여기서 호출되지 않음.
        """
        rid = request_id_var.get()
        record = ctx.record

        # 타임아웃 등으로 start만 호출되고 end가 안 된 구간을 timeout으로 마감.
        # 라이프사이클 순서가 pool → dns → tcp 이므로, 앞 단계가 timeout이면
        # 뒤 단계는 실제로 시작되지 않은 것 → idle로 리셋.
        if record.pool.status == "running":
            record.pool.mark_timeout()
            record.dns.reset()
            record.tcp.reset()
        elif record.dns.status == "running":
            record.dns.mark_timeout()
            record.tcp.reset()
        elif record.tcp.status == "running":
            record.tcp.mark_timeout()

        record.request.mark_timeout()
        record.error = str(params.exception)
        logger.error(
            f"[{rid}] [REQ ERROR] {params.method} {params.url} → {params.exception} "
            f"(total={record.request.elapsed_ms}ms, pool={record.pool.elapsed_ms}ms, "
            f"dns={record.dns.elapsed_ms}ms, tcp={record.tcp.elapsed_ms}ms)"
        )

    return trace_config
