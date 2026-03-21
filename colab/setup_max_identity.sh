#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="${1:-/content/foocus_pro}"

run_required() {
  echo ">> $*"
  "$@"
}

run_optional() {
  echo ">> $*"
  "$@" || true
}

install_onnxruntime_gpu() {
  echo ">> Installing ONNX Runtime GPU (best effort)"
  python -m pip install onnxruntime-gpu==1.17.0 \
    --index-url=https://pkgs.dev.azure.com/onnxruntime/onnxruntime/_packaging/onnxruntime-cuda-12/pypi/simple \
    && return 0
  python -m pip install onnxruntime-gpu && return 0
  python -m pip install onnxruntime && return 0
  return 1
}

echo "[1/5] Upgrading pip tooling..."
run_required python -m pip install --upgrade pip setuptools wheel

echo "[2/5] Installing quality backend dependencies..."
run_optional python -m pip install -r "${ROOT_DIR}/colab/requirements_quality.txt"
install_onnxruntime_gpu || echo "WARN: could not install ONNX Runtime GPU; CPU fallback may be used."

echo "[3/5] Preparing patched roop backend..."
if [ ! -d /content/roop_colab ]; then
  run_required git clone --depth 1 https://github.com/dream80/roop_colab.git /content/roop_colab
fi
run_required rm -rf /content/roop
run_required cp -r /content/roop_colab/roop /content/roop

echo "[4/5] Installing roop runtime dependencies..."
run_optional python -m pip install -r /content/roop/requirements.txt
run_optional python -m pip install numpy pillow opencv-python-headless insightface psutil tqdm onnx gfpgan
install_onnxruntime_gpu || echo "WARN: ONNX Runtime GPU install failed after roop deps."

echo "[5/5] Downloading roop models..."
run_required mkdir -p /content/roop/models
if [ ! -f /content/roop/models/inswapper_128.onnx ]; then
  run_optional wget -q -O /content/roop/models/inswapper_128.onnx \
    https://github.com/dream80/roop_colab/releases/download/v0.0.1/inswapper_128.onnx
fi
if [ ! -f /content/roop/models/GFPGANv1.4.pth ]; then
  run_optional wget -q -O /content/roop/models/GFPGANv1.4.pth \
    https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth
fi

echo ""
echo "Done. Next run these commands in Colab:"
echo "  nohup python -m uvicorn colab.arcface_similarity_server:app --host 0.0.0.0 --port 8890 >/content/arcface.log 2>&1 &"
echo "  python -m colab.launch_ultimate --share --port 7860"
