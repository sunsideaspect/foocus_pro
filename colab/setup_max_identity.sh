#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/content/foocus_pro}"

echo "[1/4] Installing quality backend dependencies..."
python -m pip install -r "${ROOT_DIR}/colab/requirements_quality.txt"

echo "[2/4] Cloning roop backend (if missing)..."
if [ ! -d /content/roop ]; then
  git clone https://github.com/s0md3v/roop.git /content/roop
fi

echo "[3/4] Installing roop dependencies..."
python -m pip install -r /content/roop/requirements.txt

echo "[4/4] Downloading roop models..."
mkdir -p /content/roop/models
if [ ! -f /content/roop/models/inswapper_128.onnx ]; then
  wget -q -O /content/roop/models/inswapper_128.onnx \
    https://github.com/dream80/roop_colab/releases/download/v0.0.1/inswapper_128.onnx
fi
if [ ! -f /content/roop/models/GFPGANv1.4.pth ]; then
  wget -q -O /content/roop/models/GFPGANv1.4.pth \
    https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth
fi

echo ""
echo "Done. Next run these commands in Colab:"
echo "  nohup python -m uvicorn colab.arcface_similarity_server:app --host 0.0.0.0 --port 8890 >/content/arcface.log 2>&1 &"
echo "  python -m colab.launch_colab --share --port 7860"
