# Identity Studio Architecture (MVP v1)

## Components

- `apps/web` — Next.js UI (status polling, character creation, gallery).
- `apps/api` — FastAPI API for auth, characters, jobs, results, health.
- `workers/photo` — Python worker for photo generation via Foocus adapter.
- `workers/video` — Python worker stub for video contract.
- `infra/docker-compose.yml` — local orchestration for postgres/redis/minio/api/web/workers.

## Data Flow

1. User creates a character profile with reference images.
2. User submits a photo/video job from web to API.
3. API stores job in Postgres and enqueues job id to Redis.
4. Worker pulls queue item, runs generation pipeline, uploads output to MinIO.
5. Worker writes status/metadata/result location back to Postgres.
6. Web polls job status and displays results in gallery.

## Foocus compatibility

- Adapter supports:
  - `mock` mode (default for local smoke tests),
  - `http` mode (calls Foocus-compatible HTTP endpoint),
  - `cli` mode (executes Foocus command).
- Prompt/model/cfg/steps/seed metadata is preserved end-to-end.
