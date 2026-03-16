from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Character, Job, JobStatus, JobType


def create_character(
    db: Session, *, owner_id: str, name: str, description: str | None, references: list[str]
) -> Character:
    character = Character(
        owner_id=owner_id,
        name=name,
        description=description,
        references=references,
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


def get_character(db: Session, *, character_id: str, owner_id: str) -> Character | None:
    stmt = select(Character).where(Character.id == character_id, Character.owner_id == owner_id)
    return db.execute(stmt).scalar_one_or_none()


def get_idempotent_job(
    db: Session, *, owner_id: str, job_type: JobType, idempotency_key: str
) -> Job | None:
    stmt = select(Job).where(
        Job.owner_id == owner_id,
        Job.job_type == job_type,
        Job.idempotency_key == idempotency_key,
    )
    return db.execute(stmt).scalar_one_or_none()


def create_job(
    db: Session,
    *,
    owner_id: str,
    job_type: JobType,
    character_id: str,
    payload: dict,
    idempotency_key: str | None,
) -> Job:
    job = Job(
        owner_id=owner_id,
        job_type=job_type,
        status=JobStatus.queued,
        character_id=character_id,
        payload=payload,
        idempotency_key=idempotency_key,
        attempts=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, *, job_id: str, owner_id: str) -> Job | None:
    stmt = select(Job).where(Job.id == job_id, Job.owner_id == owner_id)
    return db.execute(stmt).scalar_one_or_none()


def list_jobs(db: Session, *, owner_id: str, limit: int = 50) -> list[Job]:
    stmt = (
        select(Job)
        .where(Job.owner_id == owner_id)
        .order_by(desc(Job.created_at))
        .limit(min(limit, 200))
    )
    return list(db.execute(stmt).scalars().all())
