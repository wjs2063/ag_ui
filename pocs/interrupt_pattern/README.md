# LangGraph Interrupt + Postgres + A2A POC

LangGraph `interrupt()` 패턴 3종(str / dict / 구조화 dict) 을 Postgres 체크포인터 위에서
시연하고, FastAPI 채팅 API + 공식 `a2a-sdk` 서버/클라이언트까지 한 그래프로 묶은 POC.

## 흐름

```
START → ask_name (str interrupt) → confirm (dict interrupt) → tool_review (structured dict interrupt) → respond → END
```

각 노드의 `interrupt()` 페이로드:

| 노드          | 페이로드                                                                              |
|---------------|---------------------------------------------------------------------------------------|
| `ask_name`    | `"이름을 알려주세요"` (순수 str)                                                       |
| `confirm`     | `{"type": "confirm", "question": "...", "options": ["yes", "no"]}` (plain dict)        |
| `tool_review` | `ToolReviewRequest.model_dump()` — `{"type", "tool", "args", "reason"}` (구조화 dict)  |

## 빠른 시작

```bash
cd /Users/jeonjaehyeon/Desktop/개발/projects/ai_project/ai_poc
uv sync

# Postgres 가 docker 로 돌고 있다고 가정 (postgres:changethis@localhost:5432/app)
# 다른 DSN을 쓰려면 INTERRUPT_POC_DATABASE_URL 환경변수 설정

# 자동 테스트 11종 (필수)
uv run pytest pocs/interrupt_pattern/tests -v
```

## FastAPI 수동 실행

```bash
uv run uvicorn pocs.interrupt_pattern.main:app --port 8001
```

클라이언트는 **`/chat` 한 엔드포인트** 만 안다. 응답 모양은 항상
`{thread_id, message, done}` — `message` 는 서버가 다음에 묻는 질문(str 또는 dict)
이거나 최종 답변. `done=true` 면 대화 종료. 클라이언트는 LangGraph 의 `interrupt`
개념을 알 필요가 없다.

```bash
# 1) 첫 호출 — thread_id 미지정 → 서버 발급
curl -X POST localhost:8001/chat -H 'Content-Type: application/json' \
  -d '{"message": "hi"}'
# → {"thread_id":"<발급 id>", "message":"이름을 알려주세요", "done":false}

# 2) 동일 thread_id 로 다음 발화 → 다음 질문(dict)
curl -X POST localhost:8001/chat -H 'Content-Type: application/json' \
  -d '{"thread_id":"<위 id>", "message":"재현"}'
# → {"thread_id":"...", "message":{"type":"confirm","question":"재현님, 계속 진행할까요?","options":["yes","no"]}, "done":false}

# 3) confirm 답변 (dict 그대로 보냄) → 다음 질문(구조화 dict)
curl -X POST localhost:8001/chat -H 'Content-Type: application/json' \
  -d '{"thread_id":"...", "message":{"choice":"yes"}}'
# → {"thread_id":"...", "message":{"type":"tool_review","tool":"send_email","args":{...},"reason":"..."}, "done":false}

# 4) 도구 검토 결정 → 최종 답변(str), done=true
curl -X POST localhost:8001/chat -H 'Content-Type: application/json' \
  -d '{"thread_id":"...", "message":{"action":"approve","note":"OK"}}'
# → {"thread_id":"...", "message":"재현님, 진행 의사: yes. 도구 검토: approve (note: OK)", "done":true}
```

상태 디버그:
```bash
curl localhost:8001/state/<thread_id>
```

## A2A 수동 실행

서버:
```bash
uv run python -m pocs.interrupt_pattern.a2a_server
# 127.0.0.1:9999 에서 listen
```

다른 셸에서 카드 조회:
```bash
curl localhost:9999/.well-known/agent-card.json | jq .
```

클라이언트 헬퍼는 `pocs/interrupt_pattern/a2a_client/client.py` 의 `send_text()` 사용:

```python
import asyncio, uuid, httpx
from pocs.interrupt_pattern.a2a_client.client import send_text

async def main():
    async with httpx.AsyncClient() as c:
        ctx = f"ctx-{uuid.uuid4().hex[:8]}"
        r = await send_text(c, "http://127.0.0.1:9999", "hi", context_id=ctx)
        task_id = r["result"]["id"]
        r = await send_text(c, "http://127.0.0.1:9999", "재현",
                            task_id=task_id, context_id=ctx)
        r = await send_text(c, "http://127.0.0.1:9999", '{"choice":"yes"}',
                            task_id=task_id, context_id=ctx)
        r = await send_text(c, "http://127.0.0.1:9999",
                            '{"action":"approve","note":"OK"}',
                            task_id=task_id, context_id=ctx)
        print(r["result"]["status"]["state"])
        print(r["result"]["status"]["message"]["parts"][0]["text"])

asyncio.run(main())
```

## 환경변수

| 변수                              | 기본값                                              |
|-----------------------------------|-----------------------------------------------------|
| `INTERRUPT_POC_DATABASE_URL`      | `postgresql://postgres:changethis@localhost:5432/app` |
| `INTERRUPT_POC_FASTAPI_HOST/PORT` | `127.0.0.1` / `8001`                                |
| `INTERRUPT_POC_A2A_HOST/PORT`     | `127.0.0.1` / `9999`                                |

## 주요 파일

- `state.py` — `ChatState` TypedDict
- `nodes.py` — 세 가지 `interrupt()` 패턴 + Pydantic 검증
- `graph.py` — `build_graph(checkpointer)` 팩토리
- `checkpointer.py` — `AsyncConnectionPool` 소유 + `AsyncPostgresSaver.setup()` (lifespan)
- `main.py` — 단일 `/chat` 엔드포인트. 응답 `{thread_id, message, done}`. interrupt 는 서버 내부 메커니즘으로만 노출 안됨
- `a2a_server/executor.py` — `LangGraphExecutor` (interrupt → `input_required` 매핑)
- `a2a_server/app.py` — `A2AStarletteApplication.build()` + lifespan
- `a2a_client/client.py` — `get_agent_card()`, `send_text()` 헬퍼
- `tests/` — pytest (FastAPI: 7건 / A2A: 4건)

## 주의

- psycopg 풀에 **`autocommit=True`, `prepare_threshold=0`, `row_factory=dict_row`** 셋 다 필수
- A2A 첫 호출에는 **`task_id` 를 보내지 말 것** (서버가 발급). 이후 호출에는 응답 `result.id` 를 전달
- 테스트는 매번 checkpoint 테이블을 `TRUNCATE` (격리 목적)
