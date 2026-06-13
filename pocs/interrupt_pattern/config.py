import os

DATABASE_URL = os.getenv(
    "INTERRUPT_POC_DATABASE_URL",
    "postgresql://postgres:changethis@localhost:5432/app",
)

FASTAPI_HOST = os.getenv("INTERRUPT_POC_FASTAPI_HOST", "127.0.0.1")
FASTAPI_PORT = int(os.getenv("INTERRUPT_POC_FASTAPI_PORT", "8001"))

A2A_HOST = os.getenv("INTERRUPT_POC_A2A_HOST", "127.0.0.1")
A2A_PORT = int(os.getenv("INTERRUPT_POC_A2A_PORT", "9999"))

OPENAI_MODEL = os.getenv("INTERRUPT_POC_OPENAI_MODEL", "gpt-4o-mini")
