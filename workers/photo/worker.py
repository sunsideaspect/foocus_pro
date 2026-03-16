import logging
import time
from datetime import datetime, timezone

from redis import Redis
from sqlalchemy import select

from adapter import generate_image
from config import get_settings
from db import create_session
from models import Job, JobStatus, JobType
from storage import upload_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker-photo")

QUEUE_NAME = "identity:queue:photo"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def process_job(job_id: str, redis: Redis) -> None:
    settings = get_settings()
    with create_session() as db:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if not job:
            logger.warning("job %s not found", job_id)
            return
        if job.job_type != JobType.photo:
            logger.warning("job %s has wrong type %s", job_id, job.job_type)
            return
        if job.status == JobStatus.completed:
            logger.info("job %s already completed, skip", job_id)
            return

        job.status = JobStatus.processing
        job.error_message = None
        job.attempts = (job.attempts or 0) + 1
        job.updated_at = utcnow()
        db.add(job)
        db.commit()

        try:
            result = generate_image(job.payload)
            object_key = f"photo/{job.id}.png"
            upload_image(object_key, result.image_bytes)

            job.status = JobStatus.completed
            job.job_metadata = result.metadata
            job.result_object_key = object_key
            job.error_message = None
            job.updated_at = utcnow()
            db.add(job)
            db.commit()
            logger.info("job %s completed", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("job %s failed: %s", job_id, exc)
            job.error_message = str(exc)
            job.updated_at = utcnow()
            if job.attempts < settings.job_max_retries:
                backoff_seconds = min(2**job.attempts, 15)
                job.status = JobStatus.queued
                db.add(job)
                db.commit()
                time.sleep(backoff_seconds)
                redis.lpush(QUEUE_NAME, job_id)
                logger.info("job %s re-queued for retry %s", job_id, job.attempts)
            else:
                job.status = JobStatus.failed
                db.add(job)
                db.commit()
                logger.info("job %s marked failed after retries", job_id)


def run() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("photo worker started; queue=%s mode=%s", QUEUE_NAME, settings.foocus_adapter_mode)

    while True:
        _, job_id = redis.brpop(QUEUE_NAME, timeout=0)
        process_job(job_id, redis)


if __name__ == "__main__":
    run()
