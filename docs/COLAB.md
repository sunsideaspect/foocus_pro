# Colab Quickstart (Gradio public link)

Goal: run one Colab notebook and get a ready public Gradio URL, similar to Foocus flow.

## Option A: Open local notebook in Colab

Use `colab/Identity_Studio_Colab.ipynb`.

Recommended stable launcher: `colab/Identity_Studio_Colab_Stable.ipynb`.
Maximum-quality locked launcher: `colab/Identity_Studio_Colab_Ultimate.ipynb`.

## Option B: Manual cells

```python
!rm -rf /content/foocus_pro
!git clone -b cursor/identity-studio-ed79 https://github.com/sunsideaspect/foocus_pro.git /content/foocus_pro
%cd /content/foocus_pro
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

## "Max Identity Quality" quick path

Install optional high-quality backends (roop + ArcFace scorer):

```python
!bash colab/setup_max_identity.sh /content/foocus_pro
!nohup python -m uvicorn colab.arcface_similarity_server:app --host 0.0.0.0 --port 8890 >/content/arcface.log 2>&1 &
```

Then in UI:

1. Choose preset `max_identity_quality` (or `max_identity_vivid`).
2. Click `Apply quality preset`.
3. Upload identity reference image.
4. Keep face swap mode = `cli` and scorer mode = `http`.

Default CLI template for roop in this preset:

```bash
python /content/roop/run.py --execution-provider cuda -s {source} -t {target} -o {output} --frame-processor face_swapper face_enhancer --similar-face-distance 0.78
```

## Stable notebook link pattern

```
https://colab.research.google.com/github/sunsideaspect/foocus_pro/blob/cursor/identity-studio-ed79/colab/Identity_Studio_Colab_Stable.ipynb
```

## Ultimate notebook link

```
https://colab.research.google.com/github/sunsideaspect/foocus_pro/blob/cursor/identity-studio-ed79/colab/Identity_Studio_Colab_Ultimate.ipynb
```

Fresh (cache-bypass) ultimate notebook:

```
https://colab.research.google.com/github/sunsideaspect/foocus_pro/blob/cursor/identity-studio-ed79/colab/Identity_Studio_Colab_Ultimate_Fresh.ipynb
```
