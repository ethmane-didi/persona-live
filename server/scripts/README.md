# server/scripts: GPU server setup

`runpod-setup.sh` (added in phase 1) prepares a fresh RunPod GPU instance:
system packages, Python env, PersonaPlex install and weight download.

- **Run on the GPU server only:** `bash server/scripts/runpod-setup.sh`
- Never run this on the local Mac. It downloads multi-GB model weights.
