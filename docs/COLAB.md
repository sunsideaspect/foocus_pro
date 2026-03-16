# Colab Quickstart (Gradio public link)

Goal: run one Colab notebook and get a ready public Gradio URL, similar to Foocus flow.

## Option A: Open local notebook in Colab

Use `colab/Identity_Studio_Colab.ipynb`.

## Option B: Manual cells

```python
!git clone https://github.com/sunsideaspect/foocus_pro.git
%cd foocus_pro
!pip install -r colab/requirements.txt
!python -m colab.launch_colab --share --port 7860
```

After the last command, Gradio prints a public URL.

## Foocus backend compatibility modes

In Gradio UI (`Foocus Adapter` section):

- `mock` — fast local placeholder generation for smoke runs.
- `http` — calls Foocus-compatible HTTP endpoint.
- `cli` — executes Foocus CLI command.

For parity with `foocus_new`, use `http` or `cli` adapter against your Foocus runtime.

## Strict Identity mode (2-stage)

In `Strict Identity (2-stage)` block:

1. Upload a reference face image (the identity anchor).
2. Stage A: generation receives `identity_reference_path` in payload.
3. Stage B: optional post-process face swap (`none|http|cli`).
4. Optional similarity scorer (`http`) runs auto-retries until threshold.

Suggested usage:

- set `strict identity mode = ON`
- `post-process face swap mode = http` (or `cli`)
- `similarity scorer mode = http`
- threshold around `0.72-0.82` depending on backend
- max attempts `3-6`

HTTP contracts (expected):

- Face swap endpoint returns image bytes or JSON with `image_base64`.
- Similarity endpoint returns JSON with one of fields:
  - `similarity`
  - `score`
  - `identity_score`
