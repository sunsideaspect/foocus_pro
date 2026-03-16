import logging

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.crud import (
    create_character,
    create_job,
    get_character,
    get_idempotent_job,
    get_job,
    list_jobs,
)
from app.db import engine, get_db
from app.models import Base, Job, JobType
from app.queue import enqueue_job, get_redis
from app.schemas import (
    CharacterCreateRequest,
    CharacterResponse,
    JobResponse,
    JobResultResponse,
    PhotoJobRequest,
    VideoJobRequest,
)
from app.storage import create_presigned_get_url, ensure_bucket_exists

settings = get_settings()
app = FastAPI(title="Identity Studio API", version="0.1.0")
logger = logging.getLogger("identity-studio-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def to_job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        owner_id=job.owner_id,
        job_type=job.job_type,
        status=job.status,
        character_id=job.character_id,
        payload=job.payload,
        metadata=job.metadata,
        error_message=job.error_message,
        attempts=job.attempts,
        result_object_key=job.result_object_key,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    try:
        ensure_bucket_exists()
    except Exception as exc:  # noqa: BLE001
        logger.warning("minio bucket check skipped on startup: %s", exc)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    redis: Redis = get_redis()
    db.execute(text("SELECT 1"))
    redis.ping()
    return {"status": "ok", "service": "identity-studio-api"}


@app.post("/characters", response_model=CharacterResponse)
def post_characters(
    payload: CharacterCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> CharacterResponse:
    character = create_character(
        db,
        owner_id=user_id,
        name=payload.name,
        description=payload.description,
        references=payload.references,
    )
    return CharacterResponse(
        id=character.id,
        owner_id=character.owner_id,
        name=character.name,
        description=character.description,
        references=character.references,
        created_at=character.created_at,
        updated_at=character.updated_at,
    )


@app.get("/characters/{character_id}", response_model=CharacterResponse)
def get_character_by_id(
    character_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> CharacterResponse:
    character = get_character(db, character_id=character_id, owner_id=user_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterResponse(
        id=character.id,
        owner_id=character.owner_id,
        name=character.name,
        description=character.description,
        references=character.references,
        created_at=character.created_at,
        updated_at=character.updated_at,
    )


@app.post("/jobs/photo", response_model=JobResponse)
def post_photo_job(
    payload: PhotoJobRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> JobResponse:
    character = get_character(db, character_id=payload.character_id, owner_id=user_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if payload.idempotency_key:
        existing = get_idempotent_job(
            db,
            owner_id=user_id,
            job_type=JobType.photo,
            idempotency_key=payload.idempotency_key,
        )
        if existing:
            return to_job_response(existing)

    job = create_job(
        db,
        owner_id=user_id,
        job_type=JobType.photo,
        character_id=payload.character_id,
        payload=payload.model_dump(exclude={"idempotency_key"}),
        idempotency_key=payload.idempotency_key,
    )
    enqueue_job(JobType.photo, job.id)
    return to_job_response(job)


@app.post("/jobs/video", response_model=JobResponse)
def post_video_job(
    payload: VideoJobRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> JobResponse:
    character = get_character(db, character_id=payload.character_id, owner_id=user_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if payload.idempotency_key:
        existing = get_idempotent_job(
            db,
            owner_id=user_id,
            job_type=JobType.video,
            idempotency_key=payload.idempotency_key,
        )
        if existing:
            return to_job_response(existing)

    job = create_job(
        db,
        owner_id=user_id,
        job_type=JobType.video,
        character_id=payload.character_id,
        payload=payload.model_dump(exclude={"idempotency_key"}),
        idempotency_key=payload.idempotency_key,
    )
    enqueue_job(JobType.video, job.id)
    return to_job_response(job)


@app.get("/jobs", response_model=list[JobResponse])
def get_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> list[JobResponse]:
    jobs = list_jobs(db, owner_id=user_id, limit=limit)
    return [to_job_response(job) for job in jobs]


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_by_id(
    job_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> JobResponse:
    job = get_job(db, job_id=job_id, owner_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return to_job_response(job)


@app.get("/jobs/{job_id}/result", response_model=JobResultResponse)
def get_job_result(
    job_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> JobResultResponse:
    job = get_job(db, job_id=job_id, owner_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    presigned_url = None
    if job.result_object_key:
        presigned_url = create_presigned_get_url(job.result_object_key)

    return JobResultResponse(
        id=job.id,
        status=job.status,
        metadata=job.metadata,
        object_key=job.result_object_key,
        presigned_url=presigned_url,
    )
