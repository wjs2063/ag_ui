"""
공개 API 호출 예제 (aiohttp_wrapper + trace)

실행: python -m ai_poc.utils.aiohttps.example (프로젝트 루트에서)
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from ai_poc.utils.aiohttps.aiohttp_wrapper import AioHttpClient, DetailedClientResponseError

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)

# jsonplaceholder: 누구나 사용 가능한 공개 REST API
API_URL = "https://jsonplaceholder.typicode.com/posts/1"


async def main() -> None:
    client = AioHttpClient()
    await client.initialize_session()

    try:
        # --- 정상 요청 ---
        result = await client.get(API_URL)
        if result:
            print(f"\n=== 정상 응답 ===")
            print(f"title : {result.get('title')}")
            print(f"body  : {result.get('body', '')[:100]}")

        # --- 404 요청 (DetailedClientResponseError 확인) ---
        print("\n=== 404 요청 테스트 ===")
        try:
            await client.get("https://jsonplaceholder.typicode.com/posts/99999")
        except DetailedClientResponseError as e:
            print(f"status        : {e.status}")
            print(f"method        : {e.request_info.method}")
            print(f"url           : {e.request_info.url}")
            print(f"message       : {e.message}")
            print(f"response_body : {e.response_body}")

    finally:
        await client.close_session()


if __name__ == "__main__":
    asyncio.run(main())
