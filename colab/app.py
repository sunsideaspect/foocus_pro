import io
import json
import random
import sqlite3
import subprocess
from datetime import datetime, timezone
import os
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
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    metadata = {
        "adapter_mode": "mock",
        "prompt": payload["prompt"],
        "negative_prompt": payload["negative_prompt"],
        "model": payload["model"],
        "cfg_scale": payload["cfg_scale"],
        "steps": payload["steps"],
        "seed": seed,
        "width": width,
        "height": height,
    }
    return buffer.getvalue(), metadata


def _generate_http(payload: dict[str, Any], foocus_http_url: str) -> tuple[bytes, dict[str, Any]]:
    response = requests.post(foocus_http_url, json=payload, timeout=240)
    response.raise_for_status()
    metadata = {
        "adapter_mode": "http",
        "prompt": payload["prompt"],
        "negative_prompt": payload["negative_prompt"],
        "model": payload["model"],
        "cfg_scale": payload["cfg_scale"],
        "steps": payload["steps"],
        "seed": payload["seed"],
        "width": payload["width"],
        "height": payload["height"],
    }
    if "application/json" in response.headers.get("content-type", ""):
        body = response.json()
        image_base64 = body.get("image_base64")
        if not image_base64:
            raise gr.Error("Foocus HTTP response missing image_base64")
        import base64

        image_bytes = base64.b64decode(image_base64)
        metadata.update(body.get("metadata", {}))
        return image_bytes, metadata
    return response.content, metadata


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

    metadata = {
        "adapter_mode": "cli",
        "prompt": payload["prompt"],
        "negative_prompt": payload["negative_prompt"],
        "model": payload["model"],
        "cfg_scale": payload["cfg_scale"],
        "steps": payload["steps"],
        "seed": payload["seed"],
        "width": payload["width"],
        "height": payload["height"],
    }
    return output_file.read_bytes(), metadata


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
) -> tuple[str, Image.Image, str, list[tuple[str, str]], list[list[Any]]]:
    if not character_id:
        raise gr.Error("Create/select character first")
    if not prompt.strip():
        raise gr.Error("Prompt is required")

    if seed is None:
        seed_value = random.randint(1, 2**31 - 1)
    else:
        seed_value = int(seed)

    payload = {
        "character_id": character_id,
        "prompt": prompt.strip(),
        "negative_prompt": negative_prompt.strip(),
        "model": model.strip() or "default",
        "cfg_scale": float(cfg_scale),
        "steps": int(steps),
        "seed": seed_value,
        "width": int(width),
        "height": int(height),
    }

    adapter_mode = adapter_mode.strip().lower()
    if adapter_mode == "http":
        image_bytes, metadata = _generate_http(payload, foocus_http_url.strip())
    elif adapter_mode == "cli":
        image_bytes, metadata = _generate_cli(payload, foocus_cli_command.strip())
    else:
        image_bytes, metadata = _generate_mock(payload)

    job_id = str(uuid4())
    image_path = OUTPUT_DIR / f"{job_id}.png"
    image_path.write_bytes(image_bytes)

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
                payload["prompt"],
                payload["negative_prompt"],
                payload["model"],
                payload["cfg_scale"],
                payload["steps"],
                payload["seed"],
                payload["width"],
                payload["height"],
                json.dumps(metadata),
                str(image_path),
                utcnow(),
            ),
        )

    image = Image.open(image_path)
    status_text = f"Job completed: {job_id}"
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
            ],
            outputs=[job_status, result_image, metadata_json, gallery, history_table],
        )

        refresh_history_btn.click(fn=load_history, inputs=None, outputs=[gallery, history_table])

    return demo
