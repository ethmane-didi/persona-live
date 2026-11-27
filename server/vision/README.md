# server/vision: "describe you at the start"

When you join with your camera on, the agent grabs one frame (after ~0.8 s, so
auto-exposure has settled) and sends it here. A small vision model describes it in one
sentence, and the agent adds that sentence to Lumi's role prompt.

```text
POST http://127.0.0.1:8997/describe?width=W&height=H   body: raw RGB24 pixels
  -> {"description": "They're wearing a grey hoodie, smiling, in a room with bookshelves."}
```

**Why only once:** PersonaPlex takes text only as the role prompt when a conversation
starts. It ignores anything else the client sends, so new information can't reach her
mid-call. The prompt tells her she saw one moment and must never pretend to see more.
With the camera off, the prompt tells her she can't see you.

- **Model:** [SmolVLM2-2.2B-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct), Apache 2.0 (`VISION_MODEL` to swap). Other commercially licensed options: Florence-2 (MIT), moondream2 (Apache 2.0), Qwen2.5-VL-7B (Apache 2.0). Not Qwen2.5-VL-3B: research-only license.
- **What it's told to describe:** clothing, hair, expression, objects, setting. It's told **not** to guess age, ethnicity, gender, health, body shape or other sensitive traits.
- **Privacy:** the frame stays on the pod and isn't saved. The description is logged by the agent and service, and LiveKit agent observability may store session traces. The page says so.
- **Status: written, not yet run.** First test in the next GPU session (measure latency; it adds to the time before Lumi is "Live").

## Setup and run (GPU pod)

```bash
cd /workspace/persona-live
bash server/scripts/vision-setup.sh     # own venv at /root/venvs/vision, model into /workspace/hf_cache
source /workspace/vision.env
cd server/vision && python service.py   # wait for "vision service ready"
```
