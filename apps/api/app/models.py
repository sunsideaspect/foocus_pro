from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum as SQLEnum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobType(str, Enum):
    photo = "photo"
    video = "video"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    references: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("owner_id", "job_type", "idempotency_key", name="uq_jobs_owner_type_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    job_type: Mapped[JobType] = mapped_column(SQLEnum(JobType, name="job_type"))
    status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus, name="job_status"), index=True)
    character_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    job_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    result_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
