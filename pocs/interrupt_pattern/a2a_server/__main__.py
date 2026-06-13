import asyncio

import uvicorn

from pocs.interrupt_pattern.a2a_server.app import build_app_with_lifespan
from pocs.interrupt_pattern.config import A2A_HOST, A2A_PORT


def main():
    app = build_app_with_lifespan()
    uvicorn.run(app, host=A2A_HOST, port=A2A_PORT)


if __name__ == "__main__":
    main()
