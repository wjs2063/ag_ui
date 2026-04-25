import logging
from typing import Any
from aiohttp import (
    TraceConfig,
    TraceRequestStartParams,
    TraceRequestEndParams,
    TraceConnectionCreateStartParams,
    TraceConnectionCreateEndParams,
    TraceDnsResolveHostStartParams,
    TraceDnsResolveHostEndParams,
    TraceRequestExceptionParams,
    ClientSession,
)

logger = logging.getLogger("aiohttp.trace")


def create_trace_config() -> TraceConfig:
    """
    aiohttp TraceConfig를 생성하고, 요청 라이프사이클의 주요 시점에 로깅 콜백을 등록한다.

    요청 라이프사이클 순서:
        on_request_start
        │
        ├─ on_connection_queued_start/end   (커넥션 풀 대기)
        ├─ on_connection_reuseconn          (keep-alive 재사용 시)
        │
        ├─ on_dns_cache_hit/miss            (DNS 캐시 조회)
        ├─ on_dns_resolvehost_start/end     (실제 DNS resolve — 캐시 miss 시)
        ├─ on_connection_create_start/end   (TCP + TLS 핸드셰이크)
        │
        ├─ on_request_headers_sent          (HTTP 헤더 전송 완료)
        ├─ on_request_chunk_sent            (요청 body chunk 전송)
        ├─ on_response_chunk_received       (응답 body chunk 수신)
        ├─ on_request_redirect              (301/302 리다이렉트 시)
        │
        ├─ on_request_end                   (정상 완료)
        └─ on_request_exception             (네트워크 레벨 예외)
    """
    trace_config = TraceConfig()

    # ──────────────────────────────────────────────────────────────
    # DNS 해석
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_dns_resolvehost_start.append
    async def on_dns_start(session: ClientSession, ctx: Any, params: TraceDnsResolveHostStartParams) -> None:
        """
        DNS 이름 해석이 시작될 때 호출.

        - params.host: 해석 대상 호스트명 (e.g. "api.example.com")

        관련 TCPConnector 설정:
        - use_dns_cache=True  → 캐시 히트 시 이 콜백은 호출되지 않음 (on_dns_cache_hit이 대신 호출)
        - ttl_dns_cache=300   → 캐시 TTL(초). 만료 후 재요청 시 다시 호출됨
        - resolver            → ThreadedResolver(기본) 또는 AsyncResolver(aiodns). 어떤 resolver든 동일하게 발생
        - family=AF_INET      → resolve 결과가 IPv4로 제한되지만, 콜백 호출 여부에는 영향 없음
        """
        logger.debug(f"[DNS] resolving {params.host}")

    @trace_config.on_dns_resolvehost_end.append
    async def on_dns_end(session: ClientSession, ctx: Any, params: TraceDnsResolveHostEndParams) -> None:
        """
        DNS 이름 해석이 완료됐을 때 호출.

        - params.host: 해석 완료된 호스트명

        start ~ end 사이의 시간 = 실제 DNS resolve 소요 시간.
        이 값이 크면 ttl_dns_cache를 늘려 캐시 적중률을 높이거나, AsyncResolver(aiodns)로 전환을 고려.
        """
        logger.debug(f"[DNS] resolved  {params.host}")

    # ──────────────────────────────────────────────────────────────
    # TCP 연결
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_connection_create_start.append
    async def on_conn_start(session: ClientSession, ctx: Any, params: TraceConnectionCreateStartParams) -> None:
        """
        새 TCP 소켓(+TLS 핸드셰이크) 연결 생성이 시작될 때 호출.

        - params: 속성 없음. 호출 자체가 "새 연결을 열고 있다"는 의미.

        관련 TCPConnector 설정:
        - limit=200           → 전체 동시 연결 상한. 이 한도 내에서만 새 연결 생성 → 이 콜백 호출
        - limit_per_host=25   → 동일 (host, port, ssl) 조합당 상한. 초과 시 큐 대기 (on_connection_queued_start)
        - force_close=True    → keep-alive 비활성화. 매 요청마다 새 연결 → 이 콜백이 항상 호출됨
        - keepalive_timeout   → keep-alive 커넥션이 살아있으면 재사용 → 이 콜백 미호출 (on_connection_reuseconn 대신)
        - enable_cleanup_closed=True → SSL 비정상 종료 시 2초 후 transport abort. 풀 정리로 새 연결 빈도에 간접 영향
        """
        logger.debug("[CONN] creating connection")

    @trace_config.on_connection_create_end.append
    async def on_conn_end(session: ClientSession, ctx: Any, params: TraceConnectionCreateEndParams) -> None:
        """
        새 TCP 소켓(+TLS) 연결 생성이 완료됐을 때 호출.

        - params: 속성 없음.

        start ~ end 사이의 시간 = TCP 연결 + TLS 핸드셰이크 소요 시간.
        이 값이 크면 네트워크 지연이 높거나 TLS 협상이 느린 것.
        keep-alive를 활용해 연결 재사용을 늘리면 이 콜백 호출 빈도가 줄어든다.
        """
        logger.debug("[CONN] connection created")

    # ──────────────────────────────────────────────────────────────
    # HTTP 요청 / 응답
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_request_start.append
    async def on_request_start(session: ClientSession, ctx: Any, params: TraceRequestStartParams) -> None:
        """
        HTTP 요청이 시작될 때 호출. 모든 요청의 첫 번째 콜백.

        - params.method:  HTTP 메서드 ("GET", "POST" 등)
        - params.url:     요청 URL (yarl.URL 객체)
        - params.headers: 요청 헤더 (CIMultiDictProxy)

        리다이렉트 시 리다이렉트된 요청마다 다시 호출됨.
        ClientSession.request()를 호출하는 순간 발생.
        """
        logger.info(f"[REQ START] {params.method} {params.url}")

    @trace_config.on_request_end.append
    async def on_request_end(session: ClientSession, ctx: Any, params: TraceRequestEndParams) -> None:
        """
        HTTP 응답을 정상적으로 수신 완료했을 때 호출.

        - params.method:   요청 메서드
        - params.url:      요청 URL
        - params.headers:  요청 헤더
        - params.response: aiohttp.ClientResponse (status, headers 등 접근 가능)

        주의: raise_for_status() 이전에 호출됨.
        즉 4xx/5xx 응답이어도 "응답 수신 자체가 성공"이면 이 콜백은 호출된다.
        네트워크 에러/타임아웃처럼 응답 자체를 못 받은 경우는 on_request_exception으로 간다.
        """
        logger.info(f"[REQ END]   {params.method} {params.url} → {params.response.status}")

    # ──────────────────────────────────────────────────────────────
    # 요청 예외
    # ──────────────────────────────────────────────────────────────

    @trace_config.on_request_exception.append
    async def on_request_exception(session: ClientSession, ctx: Any, params: TraceRequestExceptionParams) -> None:
        """
        요청 처리 중 네트워크 레벨 예외가 발생했을 때 호출.

        - params.method:    요청 메서드
        - params.url:       요청 URL
        - params.headers:   요청 헤더
        - params.exception: 발생한 예외 객체 (ConnectionError, TimeoutError 등)

        주의: raise_for_status()에 의한 ClientResponseError는 여기서 호출되지 않음.
        응답 자체는 정상 수신됐으므로 on_request_end가 호출된다.

        관련 ClientTimeout 설정:
        - total        → 전체 요청 타임아웃
        - connect      → 연결 수립 타임아웃
        - sock_read    → 소켓 읽기 타임아웃
        - sock_connect → 소켓 연결 타임아웃
        이 중 하나라도 초과하면 asyncio.TimeoutError → 이 콜백 호출
        """
        logger.error(f"[REQ ERROR] {params.method} {params.url} → {params.exception}")

    return trace_config
