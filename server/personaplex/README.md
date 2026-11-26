# server/personaplex: voice brain

Wrapper around [NVIDIA PersonaPlex](https://github.com/NVIDIA/PersonaPlex), a 7B
full-duplex speech-to-speech model (built on Kyutai's Moshi).

- **Persona:** the "Runtime prompt" section of `prompts/persona.md`, sent as the text role prompt.
- **Voice:** a reference audio sample in `voices/` (e.g. `voices/lumi.wav`). Gitignored by default.
- **Weights:** `nvidia/personaplex-7b-v1`, downloaded on the GPU server only (needs `HF_TOKEN`).
- **License:** MIT code + NVIDIA Open Model License (commercial use allowed).
- **Phase:** 1

> Voice samples must be original or licensed. Never clone a real person's voice without written consent.
