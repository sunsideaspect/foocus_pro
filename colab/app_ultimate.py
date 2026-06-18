import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

import gradio as gr
import requests
from PIL import Image

from colab.app import (
    DB_PATH,
    OUTPUT_DIR,
    _compute_similarity_http,
    _run_faceswap_postprocess,
    build_history_table,
    init_storage,
    load_history,
    run_photo_job,
    save_character,
    utcnow,
)

ULTIMATE_NEGATIVE_PROMPT = (
    "blurry, blur, soft focus, lowres, low resolution, jpeg artifacts, watermark, text, logo, "
    "cartoon, anime, painting, cgi, unrealistic skin, plastic skin, bad anatomy, bad hands, "
    "extra fingers, fused fingers, malformed limbs, duplicated body parts, deformed face, cross-eye, "
    "noise, washed colors"
)


def _get_or_create_character(character_name: str, existing_character_id: str | None) -> str:
    if existing_character_id:
        return existing_character_id
    clean_name = (character_name or "Main Character").strip()
    character_id, _ = save_character(clean_name, "", "")
    return character_id


def _ultimate_generate(
    character_name: str,
    existing_character_id: str | None,
    identity_reference_image: str | None,
    base_generated_image: str | None,
    prompt: str,
) -> tuple[str, str, Any, str, list[tuple[str, str]], list[list[Any]]]:
    if not prompt.strip():
        raise gr.Error("Prompt is required")
    if not identity_reference_image:
        raise gr.Error("Identity reference image is required")
    if not Path(identity_reference_image).exists():
        raise gr.Error(f"Identity reference image does not exist: {identity_reference_image}")

    character_id = _get_or_create_character(character_name, existing_character_id)

    # Preferred path: user generates base image in Foocus UI, then uploads here for identity lock.
    if base_generated_image:
        roop_path = Path("/content/roop/run.py")
        if not roop_path.exists():
            raise gr.Error(
                "roop не встановлено. У Colab перезапусти комірку 3 (setup_max_identity.sh), "
                "потім перезапусти комірку 4 (Identity Studio)."
            )

        source_path = Path(identity_reference_image)
        target_path = Path(base_generated_image)
        if not target_path.exists():
            raise gr.Error(f"Base generated image does not exist: {target_path}")

        current_bytes = target_path.read_bytes()
        pass_meta: list[dict[str, Any]] = []
        for pass_index in range(3):
            current_bytes, meta = _run_faceswap_postprocess(
                mode="cli",
                source_image_path=source_path,
                target_image_bytes=current_bytes,
                faceswap_http_url="http://127.0.0.1:8891/swap",
                faceswap_cli_command=(
                    "python /content/roop/run.py --execution-provider cuda "
                    "-s {source} -t {target} -o {output} "
                    "--frame-processor face_swapper face_enhancer --similar-face-distance 0.76"
                ),
            )
            pass_meta.append({"pass_index": pass_index + 1, **meta})

        similarity_score: float | None = None
        try:
            similarity_score = _compute_similarity_http(
                source_image_path=source_path,
                target_image_bytes=current_bytes,
                similarity_http_url="http://127.0.0.1:8890/similarity",
            )
        except Exception:  # noqa: BLE001
            similarity_score = None

        job_id = f"ultimate-refine-{uuid4()}"
        image_path = OUTPUT_DIR / f"{job_id}.png"
        image_path.write_bytes(current_bytes)

        metadata = {
            "mode": "external_foocus_refine",
            "prompt": prompt.strip(),
            "base_generated_image": str(target_path),
            "identity_reference_image": str(source_path),
            "faceswap_passes": pass_meta,
            "similarity_score": similarity_score,
            "pipeline": "foocus_new_generation + ultimate_identity_refine",
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
                    prompt.strip(),
                    ULTIMATE_NEGATIVE_PROMPT,
                    "foocus_new_external",
                    7.0,
                    40,
                    0,
                    0,
                    0,
                    json.dumps(metadata),
                    str(image_path),
                    utcnow(),
                ),
            )

        with Image.open(image_path) as opened:
            image = opened.copy()
        gallery_items, history_rows = load_history()
        score_txt = "n/a" if similarity_score is None else f"{similarity_score:.4f}"
        status = (
            f"Ultimate refine completed (external base image). "
            f"Face-swap passes=3 | similarity={score_txt}"
        )
        return character_id, status, image, json.dumps(metadata, indent=2), gallery_items, history_rows

    raise gr.Error(
        "Спочатку згенеруй картинку в Fooocus UI (перший лінк, порт 7865), "
        "завантаж її в поле «Base generated image from Fooocus», "
        "потім натисни Generate ULTIMATE Photo. "
        "Identity Studio сам по собі не генерує фото — тільки підміняє обличчя."
    )


def _refresh_history_only() -> tuple[list[tuple[str, str]], list[list[Any]]]:
    return load_history()


def _check_backends() -> str:
    checks: list[str] = []

    try:
        response = requests.get("http://127.0.0.1:8888/health", timeout=2)
        checks.append(f"Foocus :8888 /health -> {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        checks.append(f"Foocus :8888 unreachable ({exc})")

    try:
        response = requests.get("http://127.0.0.1:7865/", timeout=2)
        checks.append(f"Foocus UI :7865 -> {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        checks.append(f"Foocus UI :7865 unreachable ({exc})")

    try:
        response = requests.get("http://127.0.0.1:8890/health", timeout=2)
        checks.append(f"ArcFace :8890 /health -> {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        checks.append(f"ArcFace :8890 unreachable ({exc})")

    roop_path = Path("/content/roop/run.py")
    checks.append(f"roop backend -> {'ok' if roop_path.exists() else 'missing'} ({roop_path})")

    return "\n".join(checks)


def _load_existing_character() -> tuple[str, str]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT id, name FROM characters ORDER BY created_at DESC LIMIT 1").fetchone()
    if row:
        return row[0], row[1]
    return "", ""


def build_demo() -> gr.Blocks:
    init_storage()
    with gr.Blocks(title="Identity Studio ULTIMATE (Colab)") as demo:
        gr.Markdown(
            """
            # Identity Studio — ULTIMATE Photoreal Mode
            Locked for best identity/detail quality:
            - strict identity ON
            - heavy retries
            - ArcFace similarity threshold
            - 3x post-process face swap pass

            Best flow (All-in-One Colab):
            1. Open **Fooocus** link (port 7865) → generate → download/save image.
            2. Here upload **identity face** + **base image from Fooocus**.
            3. Click **Generate ULTIMATE Photo** (face swap only).

            ⚠️ Do NOT click Generate with only a reference face — you will get an error (no mock).
            """
        )

        character_id_state = gr.State(value="")

        with gr.Row():
            character_name = gr.Textbox(label="Character name", value="Daniela")
            load_last_btn = gr.Button("Load last character")
            check_backends_btn = gr.Button("Check Backends")
            loaded_character_id = gr.Textbox(label="Character ID", interactive=False)

        backend_status = gr.Textbox(label="Backend status", lines=3, interactive=False)

        identity_reference_image = gr.Image(
            label="Identity reference face (required)",
            type="filepath",
        )
        base_generated_image = gr.Image(
            label="Base generated image from Foocus UI (recommended)",
            type="filepath",
        )
        prompt = gr.Textbox(
            label="Prompt",
            lines=4,
            value=(
                "ultra photorealistic cinematic portrait of a blonde woman, "
                "sharp eyes, natural skin pores, realistic hair strands, "
                "high detail body anatomy, dramatic but natural light, "
                "premium editorial photography, 85mm lens, depth of field"
            ),
        )
        generate_btn = gr.Button("Generate ULTIMATE Photo")

        job_status = gr.Textbox(label="Job status", interactive=False)
        result_image = gr.Image(label="Result image", type="pil")
        metadata_json = gr.Code(label="Metadata JSON", language="json")

        with gr.Tab("Gallery / History"):
            refresh_history_btn = gr.Button("Refresh History")
            gallery = gr.Gallery(label="Gallery", columns=3, height=420)
            history_table = build_history_table()

        load_last_btn.click(
            fn=_load_existing_character,
            inputs=None,
            outputs=[character_id_state, character_name],
        ).then(
            fn=lambda cid, _: cid,
            inputs=[character_id_state, character_name],
            outputs=[loaded_character_id],
        )

        check_backends_btn.click(
            fn=_check_backends,
            inputs=None,
            outputs=[backend_status],
        )

        generate_btn.click(
            fn=_ultimate_generate,
            inputs=[character_name, character_id_state, identity_reference_image, base_generated_image, prompt],
            outputs=[character_id_state, job_status, result_image, metadata_json, gallery, history_table],
        ).then(
            fn=lambda cid: cid,
            inputs=[character_id_state],
            outputs=[loaded_character_id],
        )

        refresh_history_btn.click(
            fn=_refresh_history_only,
            inputs=None,
            outputs=[gallery, history_table],
        )

    return demo
