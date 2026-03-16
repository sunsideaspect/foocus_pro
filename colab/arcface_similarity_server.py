import io
from functools import lru_cache

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

app = FastAPI(title="ArcFace Similarity Server", version="0.1.0")


def _read_image_bytes(image_bytes: bytes) -> np.ndarray:
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(pil_img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


@lru_cache
def _get_face_analyser():
    try:
        from insightface.app import FaceAnalysis
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "insightface is not installed. Run: pip install -r colab/requirements_quality.txt"
        ) from exc

    analyser = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    analyser.prepare(ctx_id=0, det_size=(640, 640))
    return analyser


def _largest_face_embedding(image: np.ndarray) -> np.ndarray:
    analyser = _get_face_analyser()
    faces = analyser.get(image)
    if not faces:
        raise HTTPException(status_code=422, detail="No face detected")
    best_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    embedding = np.array(best_face.normed_embedding, dtype=np.float32)
    norm = np.linalg.norm(embedding)
    if norm == 0:
        raise HTTPException(status_code=422, detail="Face embedding norm is zero")
    return embedding / norm


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/similarity")
async def similarity(
    source_image: UploadFile = File(...),
    target_image: UploadFile = File(...),
) -> dict[str, float]:
    try:
        source_bytes = await source_image.read()
        target_bytes = await target_image.read()
        source_np = _read_image_bytes(source_bytes)
        target_np = _read_image_bytes(target_bytes)
        src_embedding = _largest_face_embedding(source_np)
        tgt_embedding = _largest_face_embedding(target_np)
        score = float(np.clip(np.dot(src_embedding, tgt_embedding), -1.0, 1.0))
        # Normalize cosine from [-1, 1] to [0, 1] for easier thresholding in UI.
        normalized = (score + 1.0) / 2.0
        return {"similarity": normalized}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Similarity failed: {exc}") from exc

