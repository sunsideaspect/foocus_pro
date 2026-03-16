import base64
import io
import json
import random
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw

from config import get_settings


@dataclass
class GenerationResult:
    image_bytes: bytes
    metadata: dict[str, Any]


def _base_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": payload.get("prompt", ""),
        "negative_prompt": payload.get("negative_prompt", ""),
        "model": payload.get("model", "default"),
        "cfg_scale": payload.get("cfg_scale", 7.0),
        "steps": payload.get("steps", 28),
        "seed": payload.get("seed"),
        "width": payload.get("width", 1024),
        "height": payload.get("height", 1024),
    }


def _generate_mock_image(payload: dict[str, Any]) -> GenerationResult:
    width = int(payload.get("width", 1024))
    height = int(payload.get("height", 1024))
    seed = payload.get("seed")
    if seed is None:
        seed = random.randint(1, 2**31 - 1)

    random.seed(seed)
    img = Image.new(
        "RGB",
        (width, height),
        color=(random.randint(20, 240), random.randint(20, 240), random.randint(20, 240)),
    )
    draw = ImageDraw.Draw(img)
    prompt = str(payload.get("prompt", ""))[:120]
    draw.text((20, 20), f"MOCK FOOCUS\nseed={seed}\n{prompt}", fill=(255, 255, 255))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    metadata = _base_metadata(payload)
    metadata["seed"] = seed
    metadata["adapter_mode"] = "mock"
    return GenerationResult(image_bytes=buffer.getvalue(), metadata=metadata)


def _generate_http(payload: dict[str, Any]) -> GenerationResult:
    settings = get_settings()
    response = requests.post(settings.foocus_http_url, json=payload, timeout=180)
    response.raise_for_status()

    metadata = _base_metadata(payload)
    metadata["adapter_mode"] = "http"

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        body = response.json()
        image_base64 = body.get("image_base64")
        if not image_base64:
            raise RuntimeError("Foocus HTTP adapter response missing image_base64")
        image_bytes = base64.b64decode(image_base64)
        metadata.update(body.get("metadata", {}))
    else:
        image_bytes = response.content

    return GenerationResult(image_bytes=image_bytes, metadata=metadata)


def _generate_cli(payload: dict[str, Any]) -> GenerationResult:
    settings = get_settings()
    metadata = _base_metadata(payload)
    metadata["adapter_mode"] = "cli"

    with tempfile.TemporaryDirectory() as temp_dir:
        payload_path = Path(temp_dir) / "payload.json"
        output_path = Path(temp_dir) / "output.png"
        payload_path.write_text(json.dumps(payload), encoding="utf-8")

        command = (
            f'{settings.foocus_cli_command} --payload "{payload_path}" --output "{output_path}"'
        )
        proc = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Foocus CLI adapter failed: {proc.stderr.strip()}")

        if not output_path.exists():
            stdout = proc.stdout.strip()
            if stdout:
                output_path = Path(stdout.splitlines()[-1].strip())

        if not output_path.exists():
            raise RuntimeError("Foocus CLI adapter did not produce output image")

        return GenerationResult(image_bytes=output_path.read_bytes(), metadata=metadata)


def generate_image(payload: dict[str, Any]) -> GenerationResult:
    settings = get_settings()
    mode = settings.foocus_adapter_mode.lower().strip()

    if mode == "http":
        return _generate_http(payload)
    if mode == "cli":
        return _generate_cli(payload)
    return _generate_mock_image(payload)
