"""
통합 예제 — FastAPI + TraceMiddleware + AioHttpClient

실행:
    uvicorn ai_poc.utils.aiohttps.example:app --reload

테스트:
    curl http://localhost:8000/test
    curl http://localhost:8000/test-error
"""
import logging
import sys
import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import asyncio
import socket

from aiohttp import ClientTimeout, ClientSession, TCPConnector

from utils.aiohttps.aiohttp_wrapper import AioHttpClient, DetailedClientResponseError
from utils.aiohttps.trace import create_trace_config
from utils.aiohttps.middleware import TraceMiddleware
from utils.aiohttps.request_context import request_id_var, get_current_trace_records

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)

client = AioHttpClient()

aiohttp.ClientTimeout

@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.initialize_session()
    yield
    await client.close_session()


app = FastAPI(lifespan=lifespan)
app.add_middleware(TraceMiddleware)


@app.get("/test")
async def test_endpoint():
    """Wikipedia API 호출 — Python, FastAPI 문서 요약"""
    wiki_headers = {"User-Agent": "AioHttpTraceExample/1.0 (test@example.com)"}
    wiki_params = {
        "action": "query",
        "prop": "extracts",
        "exintro": "true",
        "explaintext": "true",
        "format": "json",
    }
    python = await client.get(
        "https://en.wikipedia.org/w/api.php",
        params={**wiki_params, "titles": "Python (programming language)"},
        headers=wiki_headers,
    )
    fastapi = await client.get(
        "https://en.wikipedia.org/w/api.php",
        params={**wiki_params, "titles": "FastAPI"},
        headers=wiki_headers,
    )

    def extract_page(result: dict) -> dict:
        pages = result.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        return {"title": page.get("title"), "extract": page.get("extract", "")[:200]}

    records = get_current_trace_records()
    return {
        "request_id": request_id_var.get(),
        "python": extract_page(python) if python else None,
        "fastapi": extract_page(fastapi) if fastapi else None,
        "trace": [r.to_dict() for r in records],
    }


@app.get("/test-error")
async def test_error_endpoint():
    """404 외부 API 호출 — DetailedClientResponseError 발생"""
    try:
        await client.get("https://jsonplaceholder.typicode.com/posts/99999")
    except DetailedClientResponseError as e:
        records = get_current_trace_records()
        return JSONResponse(
            status_code=502,
            content={
                "request_id": request_id_var.get(),
                "error": f"{e.status} {e.message}",
                "response_body": e.response_body,
                "trace": [r.to_dict() for r in records],
            },
        )


@app.get("/test-timeout")
async def test_timeout_endpoint():
    """타임아웃 테스트 — httpbin.org/delay/5 에 total=1초 타임아웃"""
    try:
        await client.get(
            "https://httpbin.org/delay/5",
            timeout=ClientTimeout(total=1),
        )
    except Exception as e:
        records = get_current_trace_records()
        return JSONResponse(
            status_code=504,
            content={
                "request_id": request_id_var.get(),
                "error_type": type(e).__name__,
                "error": str(e),
                "trace": [r.to_dict() for r in records],
            },
        )


@app.get("/test-timeout-dns")
async def test_timeout_dns():
    """
    DNS 타임아웃 테스트.
    connect=0.00001초(0.01ms)로 설정하면 DNS 해석이 끝나기 전에 타임아웃.
    기존 client는 DNS 캐시가 있으므로, 별도 커넥터를 생성하여 캐시 없이 테스트.
    """
    connector = TCPConnector(family=socket.AF_INET, ttl_dns_cache=0)
    async with ClientSession(
        connector=connector,
        trace_configs=[create_trace_config()],
        timeout=ClientTimeout(total=5, connect=0.00001),
    ) as session:
        try:
            async with session.get("https://httpbin.org/get") as resp:
                await resp.read()
        except Exception as e:
            records = get_current_trace_records()
            return JSONResponse(
                status_code=504,
                content={
                    "request_id": request_id_var.get(),
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "trace": [r.to_dict() for r in records],
                },
            )


@app.get("/test-timeout-pool")
async def test_timeout_pool():
    """
    Connection Pool 타임아웃 테스트.
    limit=1 커넥터로 동시 2건 요청 → 1건은 풀 대기 → connect 타임아웃.
    - 1번 요청: delay/3 (3초 소요, 유일한 커넥션 점유)
    - 2번 요청: delay/0 (풀에 빈 자리 없어서 대기 → 1초 후 타임아웃)
    """
    connector = TCPConnector(limit=1, limit_per_host=1, family=socket.AF_INET)
    async with ClientSession(
        connector=connector,
        trace_configs=[create_trace_config()],
    ) as session:
        async def call(url: str, timeout: ClientTimeout):
            try:
                async with session.get(url, timeout=timeout) as resp:
                    return {"status": resp.status, "error": None}
            except Exception as e:
                return {"status": None, "error": f"{type(e).__name__}: {e}"}

        results = await asyncio.gather(
            call("https://httpbin.org/delay/3", ClientTimeout(total=5)),
            call("https://httpbin.org/delay/0", ClientTimeout(total=5, connect=1)),
        )

        records = get_current_trace_records()
        return JSONResponse(
            status_code=504,
            content={
                "request_id": request_id_var.get(),
                "results": results,
                "trace": [r.to_dict() for r in records],
            },
        )


@app.get("/test-timeout-tcp")
async def test_timeout_tcp():
    """
    TCP 타임아웃 테스트.
    10.255.255.1은 라우팅 불가능한 IP → TCP SYN이 응답 없이 hang.
    DNS는 정상 완료되지만 TCP 연결에서 sock_connect=1초 타임아웃.
    """
    connector = TCPConnector(family=socket.AF_INET)
    async with ClientSession(
        connector=connector,
        trace_configs=[create_trace_config()],
        timeout=ClientTimeout(total=5, sock_connect=1),
    ) as session:
        try:
            async with session.get("http://10.255.255.1/test") as resp:
                await resp.read()
        except Exception as e:
            records = get_current_trace_records()
            return JSONResponse(
                status_code=504,
                content={
                    "request_id": request_id_var.get(),
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "trace": [r.to_dict() for r in records],
                },
            )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)