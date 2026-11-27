#!/usr/bin/env bash
# =============================================================================
# face-setup.sh: install MuseTalk 1.5 + our face service on the RunPod GPU pod.
#
# Run ON THE GPU POD, never on your Mac:
#   bash server/scripts/face-setup.sh
#
# Safe to re-run: finished steps are skipped.
#
# Where things go (same idea as runpod-setup.sh):
#   /workspace/MuseTalk          MuseTalk code + weights (~5 GB) + prepared avatars (persistent)
#   /root/venvs/face             Python 3.10 env (local disk: fast imports; rebuilt after a restart)
#
# MuseTalk needs Python 3.10 and old pinned packages (torch 2.0.1, numpy 1.23.5,
# transformers 4.39.2, mmpose 1.1.0). They clash with the agent's and the vision
# service's packages, so the face gets its own venv and runs as its own process.
# =============================================================================
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
MUSETALK_DIR="${MUSETALK_DIR:-$WORKSPACE/MuseTalk}"
MUSETALK_REPO="${MUSETALK_REPO:-https://github.com/TMElyralab/MuseTalk.git}"
MUSETALK_REF="${MUSETALK_REF:-main}"        # pin a commit here once a version works
VENV_DIR="${FACE_VENV:-/root/venvs/face}"
UV_DIR="/root/venvs/uv-tool"                # tiny venv that just holds the uv tool
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

step "0/7  Safety checks"
[[ "$(uname -s)" == "Linux" ]] || die "This script only runs on the Linux GPU pod, not on your Mac."
command -v nvidia-smi >/dev/null || die "nvidia-smi not found. Is this a GPU pod?"
[[ -d "$WORKSPACE" ]] || die "$WORKSPACE not found. Attach a volume mounted at /workspace."
info "Free on $WORKSPACE: $(df -h "$WORKSPACE" | awk 'NR==2{print $4}') (need ~8 GB)"
info "Free on container disk: $(df -h /root | awk 'NR==2{print $4}') (need ~10 GB for the venv)"

step "1/7  System packages (ffmpeg, OpenCV libraries)"
SUDO=""; [[ "$(id -u)" -ne 0 ]] && SUDO="sudo"
if ! dpkg -s ffmpeg libgl1 libglib2.0-0 python3-venv >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq --no-install-recommends ffmpeg libgl1 libglib2.0-0 python3-venv git curl >/dev/null
fi
info "ffmpeg $(ffmpeg -version | head -n1 | awk '{print $3}')"

step "2/7  uv (installs Python 3.10, which the pod image doesn't have)"
if [[ ! -x "$UV_DIR/bin/uv" ]]; then
  python3 -m venv "$UV_DIR"
  "$UV_DIR/bin/pip" install --quiet uv
fi
UV="$UV_DIR/bin/uv"
info "$("$UV" --version)"

step "3/7  MuseTalk source -> $MUSETALK_DIR"
if [[ -d "$MUSETALK_DIR/.git" ]]; then
  git -C "$MUSETALK_DIR" fetch --quiet --depth 1 origin "$MUSETALK_REF"
  git -C "$MUSETALK_DIR" checkout --quiet FETCH_HEAD
else
  git clone --quiet --depth 1 --branch "$MUSETALK_REF" "$MUSETALK_REPO" "$MUSETALK_DIR"
fi
info "At commit $(git -C "$MUSETALK_DIR" rev-parse --short HEAD)"

step "4/7  Python 3.10 venv -> $VENV_DIR"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$UV" venv --quiet --seed --python 3.10 "$VENV_DIR"   # --seed adds pip, which mim needs
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "$(python --version)"

step "5/7  PyTorch 2.0.1 (CUDA 11.8) + MuseTalk packages"
# MuseTalk's tested versions (its README). CUDA 11.8 wheels run fine on the
# pod's newer driver: drivers are backward compatible.
if ! python -c "import torch, sys; sys.exit(0 if torch.__version__.startswith('2.0.1') else 1)" 2>/dev/null; then
  pip install --quiet torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118
fi
# MuseTalk's requirements.txt minus what only training or the Gradio demo use
# (tensorflow, tensorboard, gradio: several GB). If an import fails later,
# install the full file: pip install -r $MUSETALK_DIR/requirements.txt
grep -vE '^(tensorflow|tensorboard|gradio)\b' "$MUSETALK_DIR/requirements.txt" > /tmp/musetalk-requirements.txt
pip install --quiet -r /tmp/musetalk-requirements.txt
pip install --quiet "aiohttp>=3.10,<4"                   # our face service
pip install --quiet -U openmim
# One at a time, exactly as MuseTalk's README does (mmcv needs mmengine first).
python -c "import mmpose" 2>/dev/null || {
  mim install mmengine
  mim install "mmcv==2.0.1"
  mim install "mmdet==3.1.0"
  mim install "mmpose==1.1.0"
}
python - <<'PY'
import torch
assert torch.cuda.is_available(), "PyTorch cannot see the GPU"
print(f"    torch {torch.__version__}, CUDA {torch.version.cuda}, {torch.cuda.get_device_name(0)}")
PY

step "6/7  Weights -> $MUSETALK_DIR/models (official sources, not MuseTalk's mirror)"
# MuseTalk's download_weights.sh routes Hugging Face downloads through a
# third-party mirror (HF_ENDPOINT=https://hf-mirror.com). We download only what
# inference needs, from huggingface.co directly.
unset HF_ENDPOINT
M="$MUSETALK_DIR/models"
mkdir -p "$M/musetalkV15" "$M/sd-vae" "$M/whisper" "$M/dwpose" "$M/face-parse-bisent"
dl() { huggingface-cli download "$1" --local-dir "$2" --include "${@:3}" >/dev/null; }
[[ -f "$M/musetalkV15/unet.pth" ]] || dl TMElyralab/MuseTalk "$M" "musetalkV15/musetalk.json" "musetalkV15/unet.pth"
[[ -f "$M/sd-vae/diffusion_pytorch_model.bin" ]] || dl stabilityai/sd-vae-ft-mse "$M/sd-vae" "config.json" "diffusion_pytorch_model.bin"
[[ -f "$M/whisper/pytorch_model.bin" ]] || dl openai/whisper-tiny "$M/whisper" "config.json" "pytorch_model.bin" "preprocessor_config.json"
[[ -f "$M/dwpose/dw-ll_ucoco_384.pth" ]] || dl yzd-v/DWPose "$M/dwpose" "dw-ll_ucoco_384.pth"
# Face parsing (BiSeNet). License still to check before launch: server/face/README.md, open items.
if [[ ! -f "$M/face-parse-bisent/79999_iter.pth" ]]; then
  pip install --quiet gdown
  gdown --quiet --id 154JgKpzCPW82qINcVieuPH3fZ2e0P812 -O "$M/face-parse-bisent/79999_iter.pth"
fi
[[ -f "$M/face-parse-bisent/resnet18-5c106cde.pth" ]] || \
  curl -sSL https://download.pytorch.org/models/resnet18-5c106cde.pth -o "$M/face-parse-bisent/resnet18-5c106cde.pth"
du -sh "$M" | awk '{print "    weights: "$1}'
# S3FD (face detection) is downloaded by MuseTalk itself on first use, into
# TORCH_HOME. We keep that on /workspace so it survives restarts.

step "7/7  Env file"
ENV_FILE="$WORKSPACE/face.env"
cat > "$ENV_FILE" <<EOF
# Created by face-setup.sh. Load in a new terminal with: source $ENV_FILE
export MUSETALK_DIR="$MUSETALK_DIR"
export TORCH_HOME="$WORKSPACE/torch_cache"
export FACE_VENV="$VENV_DIR"
if [[ ! -x "\$FACE_VENV/bin/python" ]]; then
  echo "Face venv not found at \$FACE_VENV (the container disk is wiped when the pod stops). Rebuilding..."
  bash "$SCRIPT_DIR/face-setup.sh" || { echo "Rebuild failed; see the errors above."; return 1; }
fi
source "\$FACE_VENV/bin/activate"
EOF

step "Done!"
cat <<EOF

  Next (once you have Lumi's likeness video and its signed release):
      source $ENV_FILE
      bash $REPO_ROOT/server/face/prepare_avatar.sh /workspace/likeness/lumi.mp4 lumi

  Then start the face service:
      source $ENV_FILE
      cd $REPO_ROOT/server/face && python service.py --avatar lumi

  Full walkthrough: server/face/README.md
EOF
