from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import JobStatus, JobType


class CharacterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    references: list[str] = Field(default_factory=list)


class CharacterResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str | None
    references: list[str]
    created_at: datetime
    updated_at: datetime


class PhotoJobRequest(BaseModel):
    character_id: str
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    model: str = "default"
    cfg_scale: float = 7.0
    steps: int = 28
    seed: int | None = None
    width: int = 1024
    height: int = 1024
    idempotency_key: str | None = Field(default=None, max_length=128)


class VideoJobRequest(BaseModel):
    character_id: str
    source_photo_job_id: str | None = None
    motion_prompt: str = Field(min_length=1)
    fps: int = 24
    seconds: int = 3
    idempotency_key: str | None = Field(default=None, max_length=128)


class JobResponse(BaseModel):
    id: str
    owner_id: str
    job_type: JobType
    status: JobStatus
    character_id: str | None
    payload: dict[str, Any]
    metadata: dict[str, Any] | None
    error_message: str | None
    attempts: int
    result_object_key: str | None
    created_at: datetime
    updated_at: datetime


class JobResultResponse(BaseModel):
    id: str
    status: JobStatus
    metadata: dict[str, Any] | None
    object_key: str | None
    presigned_url: str | None
