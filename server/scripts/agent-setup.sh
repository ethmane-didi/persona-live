#!/usr/bin/env bash
# =============================================================================
# agent-setup.sh: install the LiveKit agent (Phase 2) on the RunPod GPU pod.
#
# Run ON THE GPU POD, after runpod-setup.sh has worked:
#   bash server/scripts/agent-setup.sh
#
# The agent gets its own small venv (no torch) on the local container disk, like
# the PersonaPlex venv. A pod stop wipes it, so re-run this after a restart;
# it takes about a minute. Safe to re-run any time.
# =============================================================================
set -euo pipefail

VENV_DIR="${AGENT_VENV:-/root/venvs/agent}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT_DIR="$REPO_ROOT/server/agent"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

step "1/4  Safety checks"
[[ "$(uname -s)" == "Linux" ]] || die "This script only runs on the Linux GPU pod, not on your Mac."
PY="$(command -v python3)" || die "python3 not found."
"$PY" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] < (3, 16) else 1)' \
  || die "livekit-agents needs Python 3.10-3.15; found $("$PY" --version)."
info "Using $("$PY" --version)"

step "2/4  System packages (venv support, Opus codec)"
# Both live on the container disk, so they're gone after a pod restart.
SUDO=""; [[ "$(id -u)" -ne 0 ]] && SUDO="sudo"
if ! dpkg -s python3-venv libopus-dev >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq --no-install-recommends python3-venv python3-dev libopus-dev >/dev/null
  info "Installed python3-venv, python3-dev, libopus-dev"
else
  info "Already installed."
fi

step "3/4  Agent venv -> $VENV_DIR"
mkdir -p "$(dirname "$VENV_DIR")"
[[ -x "$VENV_DIR/bin/python" ]] || "$PY" -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel
"$VENV_DIR/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
"$VENV_DIR/bin/python" -c "import livekit.agents, livekit.rtc, sphn; from importlib.metadata import version; print('    livekit-agents', version('livekit-agents'), '/ sphn', version('sphn'))"

step "4/4  LiveKit credentials"
missing=()
for var in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET; do
  value="$(grep -E "^${var}=" "$REPO_ROOT/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  if [[ -z "$value" || "$value" == *your-* ]]; then missing+=("$var"); fi
done
if (( ${#missing[@]} )); then
  info "Not set in $REPO_ROOT/.env yet: ${missing[*]}"
  info "Copy them from your LiveKit Cloud project (Settings -> Keys) before starting the agent."
else
  info "LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET found in .env."
fi

step "Done!"
cat <<EOF

  Start the agent (with moshi.server already running on 127.0.0.1:8998):
      source $VENV_DIR/bin/activate
      cd $AGENT_DIR && python main.py dev

  Full walkthrough: server/agent/README.md
EOF
