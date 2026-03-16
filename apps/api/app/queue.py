from redis import Redis

from app.config import get_settings
from app.models import JobType

QUEUE_PREFIX = "identity:queue:"


def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def enqueue_job(job_type: JobType, job_id: str) -> None:
    redis = get_redis()
    redis.lpush(f"{QUEUE_PREFIX}{job_type.value}", job_id)
