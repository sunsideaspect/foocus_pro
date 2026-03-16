import base64
import io
import json
import os
import random
import shlex
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import gradio as gr
import requests
from PIL import Image, ImageDraw


def _resolve_runtime_home() -> Path:
    custom_home = os.environ.get("IDENTITY_STUDIO_COLAB_HOME")
    if custom_home:
        return Path(custom_home)
    default_colab_home = Path("/content")
    if default_colab_home.exists():
        return default_colab_home
    return Path("/tmp/identity_studio_colab")


RUNTIME_HOME = _resolve_runtime_home()
DB_PATH = RUNTIME_HOME / "identity_studio_colab.db"
OUTPUT_DIR = RUNTIME_HOME / "identity_studio_outputs"

STYLE_PROMPT_SUFFIXES = {
    "none": "",
    "vivid_cinematic": "vivid cinematic color palette, rich tones, high dynamic range, detailed skin texture",
    "soft_natural": "natural daylight, realistic color science, subtle contrast, authentic skin tones",
}

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "foocus_parity": {
        "adapter_mode": "http",
        "strict_identity_mode": True,
        "identity_similarity_threshold": 0.72,
        "max_identity_attempts": 3,
        "similarity_mode": "none",
        "similarity_http_url": "http://127.0.0.1:8890/similarity",
        "postprocess_faceswap_mode": "none",
        "postprocess_faceswap_passes": 1,
        "faceswap_http_url": "http://127.0.0.1:8891/swap",
        "faceswap_cli_command": "python face_swap.py --source {source} --target {target} --output {output}",
        "style_preset": "none",
    },
    "max_identity_quality": {
        "adapter_mode": "http",
        "strict_identity_mode": True,
        "identity_similarity_threshold": 0.80,
        "max_identity_attempts": 6,
        "similarity_mode": "http",
        "similarity_http_url": "http://127.0.0.1:8890/similarity",
        "postprocess_faceswap_mode": "cli",
        "postprocess_faceswap_passes": 2,
        "faceswap_http_url": "http://127.0.0.1:8891/swap",
        "faceswap_cli_command": (
            "python /content/roop/run.py --execution-provider cuda "
            "-s {source} -t {target} -o {output} "
            "--frame-processor face_swapper face_enhancer --similar-face-distance 0.78"
        ),
        "style_preset": "none",
    },
    "max_identity_vivid": {
        "adapter_mode": "http",
        "strict_identity_mode": True,
        "identity_similarity_threshold": 0.80,
        "max_identity_attempts": 6,
        "similarity_mode": "http",
        "similarity_http_url": "http://127.0.0.1:8890/similarity",
        "postprocess_faceswap_mode": "cli",
        "postprocess_faceswap_passes": 2,
        "faceswap_http_url": "http://127.0.0.1:8891/swap",
        "faceswap_cli_command": (
            "python /content/roop/run.py --execution-provider cuda "
            "-s {source} -t {target} -o {output} "
            "--frame-processor face_swapper face_enhancer --similar-face-distance 0.78"
        ),
        "style_preset": "vivid_cinematic",
    },
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_storage() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                references_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                status TEXT NOT NULL,
                prompt TEXT NOT NULL,
                negative_prompt TEXT NOT NULL,
                model TEXT NOT NULL,
                cfg_scale REAL NOT NULL,
                steps INTEGER NOT NULL,
                seed INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                image_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def parse_references(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def apply_style_preset(prompt: str, style_preset: str) -> str:
    suffix = STYLE_PROMPT_SUFFIXES.get(style_preset, "")
    clean_prompt = prompt.strip()
    if not suffix:
        return clean_prompt
    return f"{clean_prompt}, {suffix}"


def apply_quality_preset(
    preset_name: str,
) -> tuple[str, bool, float, int, str, str, str, int, str, str, str]:
    preset = QUALITY_PRESETS.get(preset_name, QUALITY_PRESETS["foocus_parity"])
    return (
        str(preset["adapter_mode"]),
        bool(preset["strict_identity_mode"]),
        float(preset["identity_similarity_threshold"]),
        int(preset["max_identity_attempts"]),
        str(preset["similarity_mode"]),
        str(preset["similarity_http_url"]),
        str(preset["postprocess_faceswap_mode"]),
        int(preset["postprocess_faceswap_passes"]),
        str(preset["faceswap_http_url"]),
        str(preset["faceswap_cli_command"]),
        str(preset["style_preset"]),
    )


def save_character(name: str, description: str, references_raw: str) -> tuple[str, str]:
    name = name.strip()
    if not name:
        raise gr.Error("Character name is required")
    character_id = str(uuid4())
    references = parse_references(references_raw)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO characters (id, name, description, references_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (character_id, name, description.strip(), json.dumps(references), utcnow()),
        )
    return character_id, f"Character created: {character_id}"


def get_character_choices() -> list[tuple[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name FROM characters ORDER BY created_at DESC"
        ).fetchall()
    return [(f"{name} ({char_id[:8]})", char_id) for char_id, name in rows]


def _base_metadata(payload: dict[str, Any], adapter_mode: str) -> dict[str, Any]:
    return {
        "adapter_mode": adapter_mode,
        "prompt": payload["prompt"],
        "negative_prompt": payload["negative_prompt"],
        "model": payload["model"],
        "cfg_scale": payload["cfg_scale"],
        "steps": payload["steps"],
        "seed": payload["seed"],
        "width": payload["width"],
        "height": payload["height"],
        "identity_reference_path": payload.get("identity_reference_path"),
    }


def _decode_image_from_response(response: requests.Response, missing_message: str) -> bytes:
    if "application/json" in response.headers.get("content-type", ""):
        body = response.json()
        image_base64 = body.get("image_base64")
        if not image_base64:
            raise gr.Error(missing_message)
        return base64.b64decode(image_base64)
    return response.content


def _generate_mock(payload: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    seed = int(payload["seed"])
    random.seed(seed)
    width = int(payload["width"])
    height = int(payload["height"])
    image = Image.new(
        "RGB",
        (width, height),
        color=(random.randint(16, 220), random.randint(16, 220), random.randint(16, 220)),
    )
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), f"MOCK FOOCUS\nseed={seed}\n{payload['prompt'][:90]}", fill=(255, 255, 255))
    if payload.get("identity_reference_path"):
        draw.text((20, 130), "identity anchor: enabled", fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), _base_metadata(payload, adapter_mode="mock")


def _generate_http(payload: dict[str, Any], foocus_http_url: str) -> tuple[bytes, dict[str, Any]]:
    response = requests.post(foocus_http_url, json=payload, timeout=240)
    response.raise_for_status()
    image_bytes = _decode_image_from_response(
        response=response,
        missing_message="Foocus HTTP response missing image_base64",
    )
    metadata = _base_metadata(payload, adapter_mode="http")
    if "application/json" in response.headers.get("content-type", ""):
        metadata.update(response.json().get("metadata", {}))
    return image_bytes, metadata


def _generate_cli(payload: dict[str, Any], foocus_cli_command: str) -> tuple[bytes, dict[str, Any]]:
    payload_file = OUTPUT_DIR / f"{uuid4()}_payload.json"
    output_file = OUTPUT_DIR / f"{uuid4()}_foocus.png"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    command = f'{foocus_cli_command} --payload "{payload_file}" --output "{output_file}"'
    process = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)
    if process.returncode != 0:
        raise gr.Error(f"Foocus CLI failed: {process.stderr.strip()}")
    if not output_file.exists():
        raise gr.Error("Foocus CLI did not return output image")

    return output_file.read_bytes(), _base_metadata(payload, adapter_mode="cli")


def _run_generation(
    payload: dict[str, Any],
    adapter_mode: str,
    foocus_http_url: str,
    foocus_cli_command: str,
) -> tuple[bytes, dict[str, Any]]:
    mode = adapter_mode.strip().lower()
    if mode == "http":
        return _generate_http(payload, foocus_http_url.strip())
    if mode == "cli":
        return _generate_cli(payload, foocus_cli_command.strip())
    return _generate_mock(payload)


def _require_existing_file(path: str | None, field_label: str) -> Path:
    if not path:
        raise gr.Error(f"{field_label} is required")
    file_path = Path(path)
    if not file_path.exists():
        raise gr.Error(f"{field_label} does not exist: {file_path}")
    return file_path


def _postprocess_faceswap_http(
    source_image_path: Path,
    target_image_bytes: bytes,
    faceswap_http_url: str,
) -> tuple[bytes, dict[str, Any]]:
    if not faceswap_http_url.strip():
        raise gr.Error("Face swap HTTP URL is required")

    with source_image_path.open("rb") as source_stream:
        files = {
            "source_image": ("source.png", source_stream, "image/png"),
            "target_image": ("target.png", target_image_bytes, "image/png"),
        }
        response = requests.post(faceswap_http_url.strip(), files=files, timeout=240)
    response.raise_for_status()
    image_bytes = _decode_image_from_response(
        response=response,
        missing_message="Face swap HTTP response missing image_base64",
    )
    return image_bytes, {"mode": "http", "endpoint": faceswap_http_url.strip()}


def _postprocess_faceswap_cli(
    source_image_path: Path,
    target_image_bytes: bytes,
    faceswap_cli_command: str,
) -> tuple[bytes, dict[str, Any]]:
    command_template = faceswap_cli_command.strip()
    if not command_template:
        raise gr.Error("Face swap CLI command is required")

    target_file = OUTPUT_DIR / f"{uuid4()}_faceswap_target.png"
    output_file = OUTPUT_DIR / f"{uuid4()}_faceswap_output.png"
    target_file.write_bytes(target_image_bytes)

    source_q = shlex.quote(str(source_image_path))
    target_q = shlex.quote(str(target_file))
    output_q = shlex.quote(str(output_file))

    if "{source}" in command_template and "{target}" in command_template and "{output}" in command_template:
        command = command_template.format(source=source_q, target=target_q, output=output_q)
    else:
        command = (
            f"{command_template} --source {source_q} --target {target_q} --output {output_q}"
        )

    process = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)
    if process.returncode != 0:
        raise gr.Error(f"Face swap CLI failed: {process.stderr.strip()}")
    if not output_file.exists():
        raise gr.Error("Face swap CLI did not produce output image")

    return output_file.read_bytes(), {"mode": "cli", "command": command_template}


def _run_faceswap_postprocess(
    mode: str,
    source_image_path: Path,
    target_image_bytes: bytes,
    faceswap_http_url: str,
    faceswap_cli_command: str,
) -> tuple[bytes, dict[str, Any]]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "http":
        return _postprocess_faceswap_http(source_image_path, target_image_bytes, faceswap_http_url)
    if normalized_mode == "cli":
        return _postprocess_faceswap_cli(source_image_path, target_image_bytes, faceswap_cli_command)
    return target_image_bytes, {"mode": "none"}


def _compute_similarity_http(
    source_image_path: Path,
    target_image_bytes: bytes,
    similarity_http_url: str,
) -> float:
    if not similarity_http_url.strip():
        raise gr.Error("Similarity HTTP URL is required")

    with source_image_path.open("rb") as source_stream:
        files = {
            "source_image": ("source.png", source_stream, "image/png"),
            "target_image": ("target.png", target_image_bytes, "image/png"),
        }
        response = requests.post(similarity_http_url.strip(), files=files, timeout=120)
    response.raise_for_status()
    body = response.json()
    raw_score = body.get("similarity")
    if raw_score is None:
        raw_score = body.get("score")
    if raw_score is None:
        raw_score = body.get("identity_score")
    if raw_score is None:
        raise gr.Error("Similarity endpoint must return one of: similarity | score | identity_score")
    return float(raw_score)


def run_photo_job(
    character_id: str,
    prompt: str,
    negative_prompt: str,
    model: str,
    cfg_scale: float,
    steps: int,
    seed: float | None,
    width: int,
    height: int,
    adapter_mode: str,
    foocus_http_url: str,
    foocus_cli_command: str,
    quality_preset: str,
    style_preset: str,
    identity_reference_image: str | None,
    strict_identity_mode: bool,
    identity_similarity_threshold: float,
    max_identity_attempts: int,
    postprocess_faceswap_mode: str,
    postprocess_faceswap_passes: int,
    faceswap_http_url: str,
    faceswap_cli_command: str,
    similarity_mode: str,
    similarity_http_url: str,
) -> tuple[str, Image.Image, str, list[tuple[str, str]], list[list[Any]]]:
    if not character_id:
        raise gr.Error("Create/select character first")
    if not prompt.strip():
        raise gr.Error("Prompt is required")

    reference_path: Path | None = None
    needs_reference = strict_identity_mode or postprocess_faceswap_mode != "none" or similarity_mode != "none"
    if needs_reference:
        reference_path = _require_existing_file(
            identity_reference_image,
            "Identity reference image",
        )

    if seed is None:
        seed_value = random.randint(1, 2**31 - 1)
    else:
        seed_value = int(seed)

    styled_prompt = apply_style_preset(prompt, style_preset)

    base_payload = {
        "character_id": character_id,
        "prompt": styled_prompt,
        "negative_prompt": negative_prompt.strip(),
        "model": model.strip() or "default",
        "cfg_scale": float(cfg_scale),
        "steps": int(steps),
        "width": int(width),
        "height": int(height),
        "identity_reference_path": str(reference_path) if reference_path else None,
    }

    max_attempts = max(1, int(max_identity_attempts))
    if not strict_identity_mode:
        max_attempts = 1

    chosen_bytes: bytes | None = None
    chosen_metadata: dict[str, Any] | None = None
    chosen_similarity: float | None = None
    best_similarity: float | None = None
    best_bytes: bytes | None = None
    best_metadata: dict[str, Any] | None = None
    attempts_info: list[dict[str, Any]] = []

    for attempt in range(1, max_attempts + 1):
        payload = {**base_payload, "seed": seed_value + (attempt - 1)}
        image_bytes, generation_metadata = _run_generation(
            payload=payload,
            adapter_mode=adapter_mode,
            foocus_http_url=foocus_http_url,
            foocus_cli_command=foocus_cli_command,
        )

        postprocess_meta = {"mode": "none"}
        if postprocess_faceswap_mode.strip().lower() != "none" and reference_path:
            pass_count = max(1, int(postprocess_faceswap_passes))
            pass_results: list[dict[str, Any]] = []
            for pass_index in range(pass_count):
                image_bytes, one_pass_meta = _run_faceswap_postprocess(
                    mode=postprocess_faceswap_mode,
                    source_image_path=reference_path,
                    target_image_bytes=image_bytes,
                    faceswap_http_url=faceswap_http_url,
                    faceswap_cli_command=faceswap_cli_command,
                )
                pass_results.append(
                    {
                        "pass_index": pass_index + 1,
                        **one_pass_meta,
                    }
                )
            postprocess_meta = {
                "mode": postprocess_faceswap_mode.strip().lower(),
                "passes": pass_results,
            }

        similarity_score: float | None = None
        if similarity_mode.strip().lower() == "http" and reference_path:
            similarity_score = _compute_similarity_http(
                source_image_path=reference_path,
                target_image_bytes=image_bytes,
                similarity_http_url=similarity_http_url,
            )

        attempt_meta = {
            **generation_metadata,
            "attempt_index": attempt,
            "postprocess_faceswap": postprocess_meta,
            "similarity_score": similarity_score,
        }
        attempts_info.append(attempt_meta)

        if similarity_score is not None and (best_similarity is None or similarity_score > best_similarity):
            best_similarity = similarity_score
            best_bytes = image_bytes
            best_metadata = attempt_meta

        # If strict mode is off, return first generated sample.
        if not strict_identity_mode:
            chosen_bytes = image_bytes
            chosen_metadata = attempt_meta
            chosen_similarity = similarity_score
            break

        # Strict mode without scorer can't auto-select by threshold.
        if similarity_mode.strip().lower() == "none":
            chosen_bytes = image_bytes
            chosen_metadata = attempt_meta
            chosen_similarity = None
            break

        if similarity_score is not None and similarity_score >= float(identity_similarity_threshold):
            chosen_bytes = image_bytes
            chosen_metadata = attempt_meta
            chosen_similarity = similarity_score
            break

    # Fall back to best attempt if threshold was not reached.
    if chosen_bytes is None:
        if best_bytes is not None and best_metadata is not None:
            chosen_bytes = best_bytes
            chosen_metadata = best_metadata
            chosen_similarity = best_similarity
        else:
            raise gr.Error("Generation failed to produce output")

    assert chosen_metadata is not None  # for type checkers
    job_id = str(uuid4())
    image_path = OUTPUT_DIR / f"{job_id}.png"
    image_path.write_bytes(chosen_bytes)

    metadata = {
        **chosen_metadata,
        "identity": {
            "quality_preset": quality_preset,
            "style_preset": style_preset,
            "original_prompt": prompt.strip(),
            "styled_prompt": styled_prompt,
            "strict_mode": bool(strict_identity_mode),
            "threshold": float(identity_similarity_threshold),
            "similarity_mode": similarity_mode.strip().lower(),
            "final_similarity": chosen_similarity,
            "postprocess_faceswap_mode": postprocess_faceswap_mode.strip().lower(),
            "postprocess_faceswap_passes": int(postprocess_faceswap_passes),
            "attempt_count": len(attempts_info),
            "attempts": attempts_info,
            "reference_image_path": str(reference_path) if reference_path else None,
        },
    }

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, character_id, status, prompt, negative_prompt, model, cfg_scale, steps, seed,
                width, height, metadata_json, image_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                character_id,
                "completed",
                base_payload["prompt"],
                base_payload["negative_prompt"],
                base_payload["model"],
                base_payload["cfg_scale"],
                base_payload["steps"],
                int(chosen_metadata["seed"]),
                base_payload["width"],
                base_payload["height"],
                json.dumps(metadata),
                str(image_path),
                utcnow(),
            ),
        )

    with Image.open(image_path) as opened:
        image = opened.copy()
    status_similarity = "n/a" if chosen_similarity is None else f"{chosen_similarity:.4f}"
    status_text = (
        f"Job completed: {job_id} | attempts={len(attempts_info)} | similarity={status_similarity}"
    )
    gallery_items, history_rows = load_history()
    return status_text, image, json.dumps(metadata, indent=2), gallery_items, history_rows


def load_history() -> tuple[list[tuple[str, str]], list[list[Any]]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, prompt, model, cfg_scale, steps, seed, image_path, metadata_json, created_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT 100
            """
        ).fetchall()

    gallery_items: list[tuple[str, str]] = []
    table_rows: list[list[Any]] = []
    for job_id, prompt, model, cfg_scale, steps, seed, image_path, metadata_json, created_at in rows:
        gallery_items.append((image_path, f"{job_id[:8]} | {model} | seed={seed}"))
        table_rows.append(
            [job_id, prompt[:80], model, cfg_scale, steps, seed, created_at, metadata_json]
        )
    return gallery_items, table_rows


def refresh_characters() -> gr.Dropdown:
    return gr.Dropdown(choices=get_character_choices())


def build_demo() -> gr.Blocks:
    init_storage()
    with gr.Blocks(title="Identity Studio (Colab)") as demo:
        gr.Markdown(
            """
            # Identity Studio — Colab Launcher
            One notebook run should produce a public Gradio URL (`share=True`) like Foocus workflow.
            Strict Identity mode runs two stages: identity-aware generation + optional face-swap refine.
            Use `max_identity_quality` preset for strongest identity lock.
            """
        )

        with gr.Tab("Character"):
            character_name = gr.Textbox(label="Character name", value="Main Character")
            character_description = gr.Textbox(label="Description", lines=2)
            character_refs = gr.Textbox(
                label="Reference URLs (one per line)",
                lines=3,
                placeholder="https://.../ref1.jpg",
            )
            create_character_btn = gr.Button("Create Character")
            character_id_out = gr.Textbox(label="Character ID", interactive=False)
            character_status_out = gr.Textbox(label="Status", interactive=False)

        with gr.Tab("Photo Job"):
            character_selector = gr.Dropdown(
                label="Character",
                choices=get_character_choices(),
                value=None,
            )
            refresh_character_btn = gr.Button("Refresh Character List")
            with gr.Row():
                quality_preset = gr.Dropdown(
                    label="Quality preset",
                    choices=list(QUALITY_PRESETS.keys()),
                    value="foocus_parity",
                )
                style_preset = gr.Radio(
                    label="Style preset",
                    choices=list(STYLE_PROMPT_SUFFIXES.keys()),
                    value="none",
                )
            apply_preset_btn = gr.Button("Apply quality preset")
            prompt = gr.Textbox(
                label="Prompt",
                lines=3,
                value="cinematic portrait, natural skin texture, 85mm lens",
            )
            negative_prompt = gr.Textbox(label="Negative Prompt", lines=2, value="")

            with gr.Row():
                model = gr.Textbox(label="Model", value="default")
                cfg_scale = gr.Slider(label="CFG Scale", minimum=1, maximum=20, value=7.0, step=0.1)
                steps = gr.Slider(label="Steps", minimum=5, maximum=80, value=28, step=1)

            with gr.Row():
                seed = gr.Number(label="Seed (optional)", value=None, precision=0)
                width = gr.Number(label="Width", value=1024, precision=0)
                height = gr.Number(label="Height", value=1024, precision=0)

            with gr.Accordion("Foocus Adapter", open=False):
                adapter_mode = gr.Radio(
                    choices=["mock", "http", "cli"],
                    value="mock",
                    label="Adapter mode",
                )
                foocus_http_url = gr.Textbox(
                    label="Foocus HTTP URL",
                    value="http://127.0.0.1:8888/generate",
                )
                foocus_cli_command = gr.Textbox(
                    label="Foocus CLI command",
                    value="python entrypoint.py",
                )

            with gr.Accordion("Strict Identity (2-stage)", open=True):
                identity_reference_image = gr.Image(
                    label="Identity reference face (e.g. Daniela)",
                    type="filepath",
                )
                strict_identity_mode = gr.Checkbox(
                    label="Enable strict identity mode",
                    value=True,
                )
                identity_similarity_threshold = gr.Slider(
                    label="Identity similarity threshold",
                    minimum=0.0,
                    maximum=1.0,
                    value=0.72,
                    step=0.01,
                )
                max_identity_attempts = gr.Slider(
                    label="Max attempts (auto-retry with new seed)",
                    minimum=1,
                    maximum=8,
                    value=3,
                    step=1,
                )

                similarity_mode = gr.Radio(
                    choices=["none", "http"],
                    value="none",
                    label="Similarity scorer mode",
                )
                similarity_http_url = gr.Textbox(
                    label="Similarity HTTP URL",
                    value="http://127.0.0.1:8890/similarity",
                )

                postprocess_faceswap_mode = gr.Radio(
                    choices=["none", "http", "cli"],
                    value="none",
                    label="Post-process face swap mode",
                )
                postprocess_faceswap_passes = gr.Slider(
                    label="Post-process face swap passes",
                    minimum=1,
                    maximum=3,
                    value=1,
                    step=1,
                )
                faceswap_http_url = gr.Textbox(
                    label="Face swap HTTP URL",
                    value="http://127.0.0.1:8891/swap",
                )
                faceswap_cli_command = gr.Textbox(
                    label="Face swap CLI command template",
                    value="python face_swap.py --source {source} --target {target} --output {output}",
                )

            run_btn = gr.Button("Generate Photo")
            job_status = gr.Textbox(label="Job status", interactive=False)
            result_image = gr.Image(label="Result image", type="pil")
            metadata_json = gr.Code(label="Metadata JSON", language="json")

        with gr.Tab("Gallery / History"):
            refresh_history_btn = gr.Button("Refresh History")
            gallery = gr.Gallery(label="Gallery", columns=3, height=420)
            history_table = gr.Dataframe(
                label="Generation history",
                headers=["job_id", "prompt", "model", "cfg", "steps", "seed", "created_at", "metadata"],
                datatype=["str", "str", "str", "number", "number", "number", "str", "str"],
                row_count=(1, "dynamic"),
                column_count=(8, "fixed"),
                interactive=False,
            )

        create_character_btn.click(
            fn=save_character,
            inputs=[character_name, character_description, character_refs],
            outputs=[character_id_out, character_status_out],
        ).then(fn=refresh_characters, inputs=None, outputs=character_selector)

        refresh_character_btn.click(fn=refresh_characters, inputs=None, outputs=character_selector)

        apply_preset_btn.click(
            fn=apply_quality_preset,
            inputs=[quality_preset],
            outputs=[
                adapter_mode,
                strict_identity_mode,
                identity_similarity_threshold,
                max_identity_attempts,
                similarity_mode,
                similarity_http_url,
                postprocess_faceswap_mode,
                postprocess_faceswap_passes,
                faceswap_http_url,
                faceswap_cli_command,
                style_preset,
            ],
        )

        run_btn.click(
            fn=run_photo_job,
            inputs=[
                character_selector,
                prompt,
                negative_prompt,
                model,
                cfg_scale,
                steps,
                seed,
                width,
                height,
                adapter_mode,
                foocus_http_url,
                foocus_cli_command,
                quality_preset,
                style_preset,
                identity_reference_image,
                strict_identity_mode,
                identity_similarity_threshold,
                max_identity_attempts,
                postprocess_faceswap_mode,
                postprocess_faceswap_passes,
                faceswap_http_url,
                faceswap_cli_command,
                similarity_mode,
                similarity_http_url,
            ],
            outputs=[job_status, result_image, metadata_json, gallery, history_table],
        )

        refresh_history_btn.click(fn=load_history, inputs=None, outputs=[gallery, history_table])

    return demo
