"""클라이언트 측 webhook 수신기 (port 9102). 완료 push 를 받아 출력한다.

실행:  uv run python -m pocs.push_demo.webhook
"""

import json

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def receive(request):
    body = await request.json()
    state = (body.get("status") or {}).get("state")
    print(f"\n🔔 [webhook] push 수신!  task={body.get('id')}  state={state}")
    print("   payload:", json.dumps(body, ensure_ascii=False)[:300])
    return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/", receive, methods=["POST"])])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9102)
