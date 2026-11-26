#!/usr/bin/env bash
# =============================================================================
# runpod-setup.sh: install NVIDIA PersonaPlex on a fresh RunPod GPU pod.
#
# Run ON THE GPU POD, never on your Mac:
#   bash server/scripts/runpod-setup.sh
#
# Safe to re-run: every step skips work that's already done.
#
# Based on the official README: https://github.com/NVIDIA/personaplex
#   1. apt install libopus-dev        (audio codec library)
#   2. pip install moshi/.            (PersonaPlex's Python package)
#   3. accept the model license on Hugging Face + export HF_TOKEN
#
# Where things go:
#   /workspace (persistent volume): PersonaPlex code + the ~16 GB of weights.
#     It survives a stop/start, but on RunPod it's often a network filesystem,
#     so reading thousands of small files from it is very slow.
#   /root/venvs (local container disk): the Python env. `import torch` opens
#     thousands of small files, which takes minutes on the network volume and
#     seconds on local disk. The container disk is wiped when the pod stops, so
#     after a restart the env is rebuilt: `source /workspace/personaplex.env`
#     re-runs this script automatically when the venv is missing.
# =============================================================================
set -euo pipefail

# ---------- Settings (override with env vars if you want) ----------
WORKSPACE="${WORKSPACE:-/workspace}"
PERSONAPLEX_REPO="${PERSONAPLEX_REPO:-https://github.com/NVIDIA/personaplex.git}"
PERSONAPLEX_REF="${PERSONAPLEX_REF:-main}"          # pin a commit/tag here for reproducible installs
PERSONAPLEX_MODEL="${PERSONAPLEX_MODEL:-nvidia/personaplex-7b-v1}"
PP_DIR="$WORKSPACE/personaplex"                     # PersonaPlex source code (persistent)
VENV_DIR="${PERSONAPLEX_VENV:-/root/venvs/personaplex}"  # Python env on LOCAL disk (fast, rebuilt after restart)
export HF_HOME="${HF_HOME:-$WORKSPACE/hf_cache}"    # where Hugging Face stores downloaded weights (persistent)
MODEL_CACHE="$HF_HOME/hub/models--${PERSONAPLEX_MODEL//\//--}"  # HF's folder for this model

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"        # persona-live repo root

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 0. Safety checks ----------
step "0/8  Safety checks"
# This guard protects the 8 GB dev Mac: never install or download models there.
[[ "$(uname -s)" == "Linux" ]] || die "This script only runs on the Linux GPU pod, not on your Mac."
command -v nvidia-smi >/dev/null || die "nvidia-smi not found. Is this a GPU pod?"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
  | while read -r line; do info "GPU: $line"; done
[[ -d "$WORKSPACE" ]] || die "$WORKSPACE not found. Attach a network/volume disk mounted at /workspace."
info "Free space on $WORKSPACE: $(df -h "$WORKSPACE" | awk 'NR==2{print $4}') (need ~25 GB for code + weights)"
mkdir -p "$(dirname "$VENV_DIR")"
info "Free space for the venv ($(dirname "$VENV_DIR")): $(df -h "$(dirname "$VENV_DIR")" | awk 'NR==2{print $4}') (need ~10 GB)"
if [[ -d "$WORKSPACE/venvs/personaplex" ]]; then
  info "Note: old venv found at $WORKSPACE/venvs/personaplex (no longer used). Remove it with: rm -rf $WORKSPACE/venvs"
fi

# ---------- 1. Hugging Face token ----------
step "1/8  Hugging Face token"
# The PersonaPlex weights are 'gated': you must accept NVIDIA's license on the
# model page once, then prove who you are with a read token.
if [[ -z "${HF_TOKEN:-}" && -f "$REPO_ROOT/.env" ]]; then
  info "Loading variables from $REPO_ROOT/.env"
  set -a; # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"; set +a
fi
SKIP_DOWNLOAD=0
if [[ -z "${HF_TOKEN:-}" || "$HF_TOKEN" == hf_your-read-token ]] && [[ -d "$MODEL_CACHE/snapshots" ]]; then
  # Rebuilding the venv after a restart: the weights are already on /workspace,
  # so the token isn't needed. Skip the download check in step 8.
  SKIP_DOWNLOAD=1
  info "No HF_TOKEN, but the weights are already cached in $MODEL_CACHE. Skipping the download step."
elif [[ -z "${HF_TOKEN:-}" || "$HF_TOKEN" == hf_your-read-token ]]; then
  die "HF_TOKEN is not set.
    1. Accept the license: https://huggingface.co/$PERSONAPLEX_MODEL
    2. Create a READ token: https://huggingface.co/settings/tokens
    3. export HF_TOKEN=hf_...   (or put it in $REPO_ROOT/.env) and re-run."
fi
if (( ! SKIP_DOWNLOAD )); then
  export HF_TOKEN
  info "HF_TOKEN found."
fi

# ---------- 2. System packages ----------
step "2/8  System packages (libopus for audio, build tools, git)"
# RunPod containers run as root and often have no sudo.
SUDO=""; [[ "$(id -u)" -ne 0 ]] && SUDO="sudo"
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq --no-install-recommends \
  libopus-dev pkg-config build-essential git python3-venv python3-dev >/dev/null
info "Installed: libopus-dev pkg-config build-essential git python3-venv python3-dev"

# ---------- 3. Python version ----------
step "3/8  Python version"
PY="$(command -v python3)" || die "python3 not found."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "PersonaPlex needs Python >= 3.10; found $("$PY" --version). Use a newer RunPod PyTorch template."
info "Using $("$PY" --version) at $PY"

# ---------- 4. Get the PersonaPlex source ----------
step "4/8  PersonaPlex source code -> $PP_DIR"
if [[ -d "$PP_DIR/.git" ]]; then
  info "Already cloned; updating to $PERSONAPLEX_REF"
  git -C "$PP_DIR" fetch --quiet --depth 1 origin "$PERSONAPLEX_REF"
  git -C "$PP_DIR" checkout --quiet FETCH_HEAD
else
  git clone --quiet --depth 1 --branch "$PERSONAPLEX_REF" "$PERSONAPLEX_REPO" "$PP_DIR"
fi
info "At commit $(git -C "$PP_DIR" rev-parse --short HEAD)"

# ---------- 5. Python virtual environment ----------
step "5/8  Python virtual environment -> $VENV_DIR"
# A venv keeps PersonaPlex's exact library versions separate from whatever the
# RunPod image ships with. It lives on the local container disk because Python
# imports are far faster there than on the /workspace network volume.
[[ -x "$VENV_DIR/bin/python" ]] || "$PY" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip wheel

# ---------- 6. PyTorch + PersonaPlex ----------
step "6/8  PyTorch + PersonaPlex (moshi package)"
# Compute capability tells us the GPU generation. 10.x/12.x = Blackwell
# (B200, RTX 50xx), which needs a CUDA 13 build of PyTorch (README, issue #2).
COMPUTE_CAP="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | tr -d ' ')"
COMPUTE_MAJOR="${COMPUTE_CAP%%.*}"
info "GPU compute capability: $COMPUTE_CAP"

# Extra packages installed next to moshi:
#   accelerate:  only needed for --cpu-offload, but it's small and handy.
#   hf_transfer: the RunPod PyTorch template sets HF_HUB_ENABLE_HF_TRANSFER=1,
#                and huggingface_hub then refuses to download without it. It's
#                also a faster downloader for the ~16 GB of weights.
EXTRA_PKGS=(accelerate hf_transfer)

if (( COMPUTE_MAJOR >= 10 )); then
  info "Blackwell GPU: following the README's extra step (PyTorch cu130)."
  pip install --quiet "$PP_DIR/moshi/." "${EXTRA_PKGS[@]}"
  pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
else
  # PersonaPlex pins torch < 2.5. Installing it first from the CUDA 12.4 index
  # (same CUDA as NVIDIA's own Dockerfile) avoids pip picking a mismatched build.
  info "Installing torch 2.4.1 (CUDA 12.4 build)."
  pip install --quiet "torch==2.4.1" --index-url https://download.pytorch.org/whl/cu124
  pip install --quiet "$PP_DIR/moshi/." "${EXTRA_PKGS[@]}"
fi

# ---------- 7. Verify the GPU is usable from Python ----------
step "7/8  Verifying PyTorch can see the GPU"
python - <<'PY'
import torch
assert torch.cuda.is_available(), "PyTorch cannot see a CUDA GPU"
props = torch.cuda.get_device_properties(0)
print(f"    torch {torch.__version__}, CUDA {torch.version.cuda}")
print(f"    {props.name}: {props.total_memory / 1024**3:.1f} GB VRAM")
if props.total_memory / 1024**3 < 30:
    print("    WARNING: under ~30 GB VRAM. If you hit 'CUDA out of memory', add --cpu-offload.")
PY
python -c "import moshi.server, moshi.offline" || die "moshi package failed to import."
info "moshi package imports OK."

# ---------- 8. Pre-download the weights ----------
step "8/8  Downloading $PERSONAPLEX_MODEL into $HF_HOME (first time: ~16 GB, a few minutes)"
# Doing this now means the server starts fast later, and you find out right away
# if the license hasn't been accepted. Already-downloaded files are skipped.
if (( SKIP_DOWNLOAD )); then
  info "Skipped (no HF_TOKEN; using the weights already in $MODEL_CACHE)."
else
python - "$PERSONAPLEX_MODEL" <<'PY'
import sys
from huggingface_hub import snapshot_download
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError

repo = sys.argv[1]
try:
    path = snapshot_download(repo)
except GatedRepoError:
    sys.exit(f"\nERROR: access denied. Accept the license at https://huggingface.co/{repo} "
             "with the same account as your HF_TOKEN, then re-run.")
except RepositoryNotFoundError:
    sys.exit(f"\nERROR: {repo} not found, or your token can't see it. Check HF_TOKEN.")
print(f"    Weights ready at {path}")
PY
fi

# ---------- Save an env file so new terminals are ready to go ----------
# The env file lives on /workspace (persistent), the venv on the container disk
# (wiped on stop). So the env file checks for the venv and rebuilds it if a
# restart wiped it. Re-running the whole script also reinstalls libopus, which
# lived on the container disk too.
ENV_FILE="$WORKSPACE/personaplex.env"
cat > "$ENV_FILE" <<EOF
# Created by runpod-setup.sh. Load in a new terminal with: source $ENV_FILE
export HF_HOME="$HF_HOME"
export PERSONAPLEX_DIR="$PP_DIR"
export PERSONAPLEX_VENV="$VENV_DIR"
if [[ ! -x "\$PERSONAPLEX_VENV/bin/python" ]]; then
  echo "Python env not found at \$PERSONAPLEX_VENV (the container disk is wiped when the pod stops)."
  echo "Rebuilding it with runpod-setup.sh (a few minutes; code and weights on /workspace are reused)..."
  bash "$SCRIPT_DIR/runpod-setup.sh" || { echo "Rebuild failed; see the errors above."; return 1; }
fi
source "\$PERSONAPLEX_VENV/bin/activate"
EOF

step "Done!"
cat <<EOF

  In every new terminal on the pod, first run:
      source $ENV_FILE

  Start the live server (open port 8998 as an HTTP port on the pod first):
      cd $PP_DIR && python -m moshi.server --host 0.0.0.0 --port 8998

  Then open:  https://<POD_ID>-8998.proxy.runpod.net
  Paste the runtime prompt, which you can print with:
      python $REPO_ROOT/server/personaplex/runtime_prompt.py

  Full walkthrough: server/personaplex/README.md
EOF
