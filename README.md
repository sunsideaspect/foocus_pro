# Identity Studio (MVP v1)

Identity Studio is a new product repository focused on:

- web UI + API + workers + queue orchestration,
- photorealistic generation with stable face identity,
- compatibility with `foocus_new` behavior via adapter modes.

`foocus_new` remains an external inference engine and behavior reference.
This repository does **not** modify generation defaults unless explicitly requested.

## Monorepo Structure

- `apps/web` — Next.js UI (character creation, job submit, polling, gallery)
- `apps/api` — FastAPI API (characters, jobs, status, result, health)
- `workers/photo` — photo worker with Foocus adapter (`mock|http|cli`)
- `workers/video` — video worker contract + stub pipeline
- `packages/shared` — TypeScript shared DTO/contracts
- `infra/docker-compose.yml` — local stack
- `docs/` — architecture notes

## MVP Endpoints

- `POST /characters`
- `GET /characters/{id}`
- `POST /jobs/photo`
- `POST /jobs/video`
- `GET /jobs/{id}`
- `GET /jobs/{id}/result`
- `GET /jobs` (history/gallery feed)
- `GET /health`

## Local Environment

1. Copy environment file:

   ```bash
   cp .env.example .env
   ```

2. Start services:

   ```bash
   docker compose -f infra/docker-compose.yml up --build
   ```

3. Open:
   - web: `http://localhost:3000`
   - api docs: `http://localhost:8000/docs`
   - minio console: `http://localhost:9001`

## Colab (ready Gradio link)

If you want Foocus-style Colab flow (run notebook -> receive public Gradio URL):

- open `colab/Identity_Studio_Colab.ipynb` in Colab,
- or use `colab/Identity_Studio_Colab_Stable.ipynb` (recommended),
- run all cells,
- the last cell runs:

```bash
python -m colab.launch_colab --share --port 7860
```

`--share` prints a public Gradio link directly in Colab output.
See `docs/COLAB.md` for quick instructions and adapter modes.
If notebook fails to find `colab/requirements.txt`, re-run with clone from branch
`cursor/identity-studio-ed79` (the notebook is already configured for this).

Colab launcher now includes **Strict Identity (2-stage)**:
- identity-anchored generation (reference face on input),
- optional post-process face swap,
- optional similarity scoring with auto-retries to hit threshold.

For strongest personal-use identity lock:
- run `bash colab/setup_max_identity.sh /content/foocus_pro`,
- start scorer: `python -m uvicorn colab.arcface_similarity_server:app --host 0.0.0.0 --port 8890`,
- in UI choose preset: `max_identity_quality` (or `max_identity_vivid`).

## Notes on Foocus Parity

Photo worker forwards payload fields (`prompt`, `negative_prompt`, `model`, `cfg_scale`, `steps`, `seed`, `width`, `height`) without mutating defaults. Adapter modes:

- `mock` — deterministic placeholder image for local smoke tests.
- `http` — POST payload JSON to `FOOCUS_HTTP_URL`.
- `cli` — executes `FOOCUS_CLI_COMMAND --payload <json> --output <png>`.

## Idempotency and Retries

- `POST /jobs/photo` and `POST /jobs/video` support `idempotency_key`.
- API returns existing job when key already exists for `(owner_id, job_type)`.
- Workers update attempts and retry until `JOB_MAX_RETRIES`.

## Smoke Test (API)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
pytest apps/api/tests -q
```
