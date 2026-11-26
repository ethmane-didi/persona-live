# server/audio2face: face animation

Runs Lumi's output audio through [NVIDIA Audio2Face-3D](https://huggingface.co/nvidia/Audio2Face-3D-v3.0)
(plus Audio2Emotion) to produce facial **blendshape weights**, not video.
The agent sends them to the browser over the LiveKit data channel, where three.js
animates the 3D head.

- **Target:** under 100 ms of drift between audio and face.
- **Data-channel message format:** TBD in phase 3.
- **License:** NVIDIA Open Model License (commercial use allowed).
- **Phase:** 3

> The 3D head must be an original or licensed asset, never a real person's likeness without written consent.
