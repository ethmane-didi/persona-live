#!/usr/bin/env bash
# =============================================================================
# vision-setup.sh: install the vision service (describes one camera frame) on
# the RunPod GPU pod.
#
# Run ON THE GPU POD, never on your Mac:
#   bash server/scripts/vision-setup.sh
#
# Own venv (needs a newer transformers than MuseTalk, and a newer
# huggingface-hub than PersonaPlex) on the local container disk. The model
# (~4.5 GB) goes into the shared Hugging Face cache on /workspace.
# Safe to re-run.
# =============================================================================
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
VENV_DIR="${VISION_VENV:-/root/venvs/vision}"
MODEL="${VISION_MODEL:-HuggingFaceTB/SmolVLM2-2.2B-Instruct}"
export HF_HOME="${HF_HOME:-$WORKSPACE/hf_cache}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

step "1/4  Safety checks"
[[ "$(uname -s)" == "Linux" ]] || die "This script only runs on the Linux GPU pod, not on your Mac."
command -v nvidia-smi >/dev/null || die "nvidia-smi not found. Is this a GPU pod?"
PY="$(command -v python3)" || die "python3 not found."

step "2/4  Venv -> $VENV_DIR"
SUDO=""; [[ "$(id -u)" -ne 0 ]] && SUDO="sudo"
dpkg -s python3-venv >/dev/null 2>&1 || { $SUDO apt-get update -qq; $SUDO apt-get install -y -qq python3-venv >/dev/null; }
[[ -x "$VENV_DIR/bin/python" ]] || "$PY" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip wheel

step "3/4  PyTorch (CUDA 12.6 build) + transformers"
python -c "import torch" 2>/dev/null || pip install --quiet torch --index-url https://download.pytorch.org/whl/cu126
pip install --quiet -r "$REPO_ROOT/server/vision/requirements.txt"
python -c "import torch; assert torch.cuda.is_available(); print('    torch', torch.__version__, torch.cuda.get_device_name(0))"

step "4/4  Model -> $HF_HOME ($MODEL)"
python - "$MODEL" <<'PY'
import sys
from huggingface_hub import snapshot_download
print("    ready at", snapshot_download(sys.argv[1]))
PY

ENV_FILE="$WORKSPACE/vision.env"
cat > "$ENV_FILE" <<EOF
# Created by vision-setup.sh. Load in a new terminal with: source $ENV_FILE
export HF_HOME="$HF_HOME"
export VISION_MODEL="$MODEL"
export VISION_VENV="$VENV_DIR"
if [[ ! -x "\$VISION_VENV/bin/python" ]]; then
  echo "Vision venv not found (the container disk is wiped when the pod stops). Rebuilding..."
  bash "$SCRIPT_DIR/vision-setup.sh" || { echo "Rebuild failed; see the errors above."; return 1; }
fi
source "\$VISION_VENV/bin/activate"
EOF

step "Done!"
cat <<EOF

  Start the vision service:
      source $ENV_FILE
      cd $REPO_ROOT/server/vision && python service.py

  Full walkthrough: server/vision/README.md
EOF
