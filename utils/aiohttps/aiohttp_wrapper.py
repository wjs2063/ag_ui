from aiohttp import ClientSession, TCPConnector, BaseConnector, ClientResponseError, RequestInfo
from typing import Protocol
import orjson
from typing import Optional, Any, Dict, Tuple
import socket
from multidict import MultiMapping
from .trace import create_trace_config, TracingResolver

class DetailedClientResponseError(ClientResponseError):
    """ClientResponseError + response_body (str, 500자 truncate)"""

    def __init__(
        self,
        request_info: RequestInfo,
        history: Tuple[Any, ...],
        *,
        status: int | None  = None,
        message: str = "",
        headers: Optional[MultiMapping[str]] = None,
        response_body: str = "",
    ) -> None:
        super().__init__(request_info, history, status=status, message=message, headers=headers)
        self.response_body = response_body[:500]


class HTTPClientSessionInterface(Protocol):

    # async def initialize_session(self) -> ClientSession:
    #     """Lifespan 시작 시 호출: 세션 풀 생성"""
    #     pass
    #
    # async def close_session(self) -> None:
    #     pass
    #
    # async def get_session(self) -> ClientSession:
    #     pass

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[dict] = None) -> Optional[dict]:
        pass

    async def post(self, url: str, json: Optional[Dict[str, Any]] = None, headers: Optional[dict] = None) -> Optional[dict]:
        pass


class AioHttpClient(HTTPClientSessionInterface):
    def __init__(self) -> None:
        self._session: Optional[ClientSession] = None

    async def initialize_session(self) -> ClientSession:
        """Lifespan 시작 시 호출: 세션 풀 생성"""
        connector = TCPConnector(
            resolver=TracingResolver(),
            limit=200,
            limit_per_host=25,
            ttl_dns_cache=300,
            family=socket.AF_INET,
            enable_cleanup_closed=True
        )
        self._session = ClientSession(
            connector=connector,
            trace_configs=[create_trace_config()],
            json_serialize=lambda x: orjson.dumps(x).decode("utf-8"),
        )

        return self._session

    async def close_session(self) -> None:
        """Lifespan 종료 시 호출"""
        if self._session:
            await self._session.close()

    # --- 공통 요청 처리 메서드 (내부용) ---
    async def _request(self, method: str, url: str, **kwargs) -> Optional[dict]:
        if not self._session:
            raise RuntimeError("Client is not initialized. Check lifespan.")
        # 기본 헤더 설정 (압축 전송 요청)
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("Accept-Encoding", "gzip, deflate")
        if method.upper() in ("POST", "PUT", "PATCH"):
            headers.setdefault("Content-Type", "application/json")

        async with self._session.request(method, url, headers=headers, **kwargs) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as e:
                body = await response.text()
                raise DetailedClientResponseError(
                    request_info=e.request_info,
                    history=e.history,
                    status=e.status,
                    message=e.message,
                    headers=e.headers,
                    response_body=body,
                ) from e

            # [Performance] bytes로 읽어서 orjson으로 파싱 (Zero-copy 지향)
            raw_bytes = await response.read()
            if not raw_bytes:
                return None
            return orjson.loads(raw_bytes)

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[dict] = None, **kwargs) -> Optional[dict]:
        return await self._request("GET", url, params=params, headers=headers, **kwargs)

    async def post(self, url: str, json: Optional[Dict[str, Any]] = None, headers: Optional[dict] = None, **kwargs) -> Optional[dict]:
        # aiohttp의 json= 파라미터는 위에서 설정한 json_serialize(orjson)를 사용함
        return await self._request("POST", url, json=json, headers=headers, **kwargs)



# 싱글톤 인스턴스 (Main에서 사용)
aiohttp_client = AioHttpClient()


def get_http_client() -> AioHttpClient:
    return aiohttp_client
