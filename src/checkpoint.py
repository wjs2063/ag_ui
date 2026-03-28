from langgraph.checkpoint.redis import RedisSaver

REDIS_URL = "redis://localhost:6379"


def get_checkpointer() -> RedisSaver:
    return RedisSaver(redis_url=REDIS_URL)
