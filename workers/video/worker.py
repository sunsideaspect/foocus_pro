import logging
import time
from datetime import datetime, timezone

from redis import Redis
from sqlalchemy import select

from config import get_settings
from db import create_session
from models import Job, JobStatus, JobType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker-video")

QUEUE_NAME = "identity:queue:video"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def process_job(job_id: str, redis: Redis) -> None:
    settings = get_settings()
    with create_session() as db:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if not job:
            logger.warning("job %s not found", job_id)
            return
        if job.job_type != JobType.video:
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
            # Stub pipeline: reserve contract and metadata while real animation is pending.
            time.sleep(1)
            job.status = JobStatus.completed
            job.metadata = {
                "pipeline": "video-stub",
                "note": "Video pipeline stub executed; replace with animation backend.",
                "input": job.payload,
            }
            job.result_object_key = None
            job.error_message = None
            job.updated_at = utcnow()
            db.add(job)
            db.commit()
            logger.info("video stub job %s completed", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("video job %s failed: %s", job_id, exc)
            job.error_message = str(exc)
            job.updated_at = utcnow()
            if job.attempts < settings.job_max_retries:
                job.status = JobStatus.queued
                db.add(job)
                db.commit()
                redis.lpush(QUEUE_NAME, job_id)
            else:
                job.status = JobStatus.failed
                db.add(job)
                db.commit()


def run() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("video worker started; queue=%s", QUEUE_NAME)
    while True:
        _, job_id = redis.brpop(QUEUE_NAME, timeout=0)
        process_job(job_id, redis)


if __name__ == "__main__":
    run()
