# server/scripts: GPU server setup

`runpod-setup.sh` prepares a fresh RunPod GPU pod for Phase 1. It installs system
packages, creates a Python venv, installs PersonaPlex, and downloads the weights.
Everything goes onto the persistent `/workspace` volume.

- **Run on the GPU pod only:** `bash server/scripts/runpod-setup.sh`
- Needs `HF_TOKEN` (env var or `.env`) and the PersonaPlex license accepted on Hugging Face.
- Refuses to run on macOS. It downloads ~16 GB of weights.
- Full walkthrough: [server/personaplex/README.md](../personaplex/README.md)
