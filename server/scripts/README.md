# server/scripts: GPU server setup

`runpod-setup.sh` prepares a fresh RunPod GPU pod for Phase 1. It installs system
packages, creates a Python venv, installs PersonaPlex, and downloads the weights.
Code and weights go on the persistent `/workspace` volume. The venv goes on the fast
local container disk (`/root/venvs/personaplex`) and is rebuilt automatically by
`source /workspace/personaplex.env` after a pod restart wipes it.

- **Run on the GPU pod only:** `bash server/scripts/runpod-setup.sh`
- Needs `HF_TOKEN` (env var or `.env`) and the PersonaPlex license accepted on Hugging Face.
- Refuses to run on macOS. It downloads ~16 GB of weights.
- Full walkthrough: [server/personaplex/README.md](../personaplex/README.md)

`agent-setup.sh` installs the Phase 2 LiveKit agent: a small venv at
`/root/venvs/agent` (no torch) with `server/agent/requirements.txt`, and a check that
the LiveKit credentials are in `.env`. Re-run it after a pod restart (about a minute).

- **Run on the GPU pod only:** `bash server/scripts/agent-setup.sh`
- Full walkthrough: [server/agent/README.md](../agent/README.md)
