import sqlite3
from pathlib import Path
from typing import Any

import gradio as gr

from colab.app import (
    DB_PATH,
    build_history_table,
    init_storage,
    load_history,
    run_photo_job,
    save_character,
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
    prompt: str,
) -> tuple[str, str, Any, str, list[tuple[str, str]], list[list[Any]]]:
    if not prompt.strip():
        raise gr.Error("Prompt is required")
    if not identity_reference_image:
        raise gr.Error("Identity reference image is required")
    if not Path(identity_reference_image).exists():
        raise gr.Error(f"Identity reference image does not exist: {identity_reference_image}")

    character_id = _get_or_create_character(character_name, existing_character_id)
    try:
        status, image, metadata, gallery_items, history_rows = run_photo_job(
            character_id=character_id,
            prompt=prompt,
            negative_prompt=ULTIMATE_NEGATIVE_PROMPT,
            model="default",
            cfg_scale=7.0,
            steps=40,
            seed=None,
            width=1024,
            height=1365,
            adapter_mode="http",
            foocus_http_url="http://127.0.0.1:8888/generate",
            foocus_cli_command="python entrypoint.py",
            quality_preset="ultimate_locked",
            style_preset="vivid_cinematic",
            identity_reference_image=identity_reference_image,
            strict_identity_mode=True,
            identity_similarity_threshold=0.82,
            max_identity_attempts=10,
            postprocess_faceswap_mode="cli",
            postprocess_faceswap_passes=3,
            faceswap_http_url="http://127.0.0.1:8891/swap",
            faceswap_cli_command=(
                "python /content/roop/run.py --execution-provider cuda "
                "-s {source} -t {target} -o {output} "
                "--frame-processor face_swapper face_enhancer --similar-face-distance 0.76"
            ),
            similarity_mode="http",
            similarity_http_url="http://127.0.0.1:8890/similarity",
        )
        return character_id, status, image, metadata, gallery_items, history_rows
    except Exception as exc:  # noqa: BLE001
        raise gr.Error(
            "Ultimate pipeline failed. Ensure these are running: "
            "Foocus HTTP on :8888, ArcFace scorer on :8890, roop backend in /content/roop. "
            f"Details: {exc}"
        ) from exc


def _refresh_history_only() -> tuple[list[tuple[str, str]], list[list[Any]]]:
    return load_history()


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

            Fill only **character name**, **reference face**, and **prompt**.
            """
        )

        character_id_state = gr.State(value="")

        with gr.Row():
            character_name = gr.Textbox(label="Character name", value="Daniela")
            load_last_btn = gr.Button("Load last character")
            loaded_character_id = gr.Textbox(label="Character ID", interactive=False)

        identity_reference_image = gr.Image(
            label="Identity reference face (required)",
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

        generate_btn.click(
            fn=_ultimate_generate,
            inputs=[character_name, character_id_state, identity_reference_image, prompt],
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
