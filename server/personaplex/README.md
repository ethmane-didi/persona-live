# server/personaplex: voice brain (Phase 1)

[NVIDIA PersonaPlex](https://github.com/NVIDIA/personaplex) is a 7B **full-duplex
speech-to-speech** model built on Kyutai's Moshi. It hears audio and speaks audio
directly, with no separate speech-to-text → LLM → text-to-speech steps. It listens
and talks at the same time, so it can say "mm-hm", get interrupted, and pause
naturally.

It's controlled by two inputs:

| Input | What it controls | Where ours comes from |
|---|---|---|
| **Text prompt** | Who the persona is (role, personality, rules) | The "Runtime prompt" section of [`prompts/persona.md`](../../prompts/persona.md) |
| **Voice prompt** | What the persona sounds like | A preset voice for now (e.g. `NATF2.pt`); later an original/licensed `voices/lumi.wav` |

- **Weights:** `nvidia/personaplex-7b-v1` on Hugging Face (gated, so you accept the license once)
- **License:** MIT code + NVIDIA Open Model License. Commercial use is allowed. The base Moshi weights are CC-BY-4.0.
- **Language:** English only

> **Everything below happens on the rented GPU pod, never on your Mac.**

---

## 1. Which GPU to rent

PersonaPlex runs in bf16 (16-bit numbers). A 7B model at 2 bytes per parameter is
**about 15–16 GB just for the weights**. On top of that come the audio codec (Mimi),
the conversation memory (KV cache) and PyTorch overhead. NVIDIA only lists one tested
GPU (A100 80 GB) and doesn't publish a minimum, so the VRAM guidance below is our
estimate:

| GPU on RunPod | VRAM | Verdict |
|---|---|---|
| **RTX A6000 / L40S** | 48 GB | **Recommended for dev.** Plenty of headroom, usually cheaper than A100 |
| A100 / H100 | 80 GB | NVIDIA's tested setup. Use it if something misbehaves on smaller cards |
| RTX 4090 / RTX A5000 / L4 | 24 GB | Probably fits, but tight. If you see `CUDA out of memory`, add `--cpu-offload` (slower) |
| RTX 50xx / B200 (Blackwell) | varies | Works, but needs a different PyTorch build. The setup script handles this |
| Anything under 24 GB | — | Don't bother |

Real-time speech needs each 80 ms audio frame generated in under 80 ms, so a fast
GPU matters as much as the VRAM. If the voice stutters, rent a faster card.

### Pod settings

1. RunPod → **Pods → Deploy** → pick the GPU.
2. **Template:** "RunPod PyTorch" (Ubuntu 22.04 + CUDA 12.x). Any template with Python ≥ 3.10 and an NVIDIA driver works.
3. **Volume disk (mounted at `/workspace`): 60 GB.** The weights (~16 GB) and Python env (~6 GB) go here. The *container* disk is wiped when the pod stops; the volume isn't.
4. **Expose HTTP ports:** add **`8998`**. RunPod then gives you a public HTTPS URL for the web UI.
5. Deploy, then click **Connect → Start Web Terminal** (or SSH).

💸 **You pay per hour while the pod runs.** Stop it when you're done. Your `/workspace` volume is kept (it costs a little storage per month).

---

## 2. Before running the script: Hugging Face access

The weights are gated, so do this once:

1. Log in at huggingface.co and **accept the license** on <https://huggingface.co/nvidia/personaplex-7b-v1>
2. Create a **Read** token at <https://huggingface.co/settings/tokens>
3. On the pod, either `export HF_TOKEN=hf_...` or put it in `persona-live/.env` (the script reads that file).

---

## 3. Run the setup script

Get this repo onto the pod. The easiest way is to push it to a private GitHub repo and
clone it into `/workspace`:

```bash
cd /workspace
git clone https://github.com/<you>/persona-live.git
cd persona-live
export HF_TOKEN=hf_...            # or create .env from .env.example
bash server/scripts/runpod-setup.sh
```

What it does, step by step (re-running is safe, since finished steps are skipped):

| Step | What happens | Why |
|---|---|---|
| 0 | Refuses to run on macOS; checks `nvidia-smi` and `/workspace` | Protects your Mac; confirms there's a GPU and a persistent disk |
| 1 | Checks `HF_TOKEN` (loads `.env` if needed) | Needed to download gated weights |
| 2 | `apt install libopus-dev …` | Opus is the audio codec the browser and server stream with |
| 3 | Checks Python ≥ 3.10 | PersonaPlex's minimum |
| 4 | Clones PersonaPlex to `/workspace/personaplex` | The model's code |
| 5 | Creates a venv at `/workspace/venvs/personaplex` | Keeps exact library versions isolated, and on the persistent disk |
| 6 | Installs PyTorch 2.4.1 (CUDA 12.4), then `pip install moshi/.` | PersonaPlex requires torch < 2.5. Blackwell GPUs get the CUDA 13 build instead |
| 7 | Checks that PyTorch sees the GPU and prints the VRAM | Catches driver or CUDA problems early |
| 8 | Downloads the weights (~16 GB) into `/workspace/hf_cache` | So the server starts fast, and a missing license acceptance shows up now |

It finishes by writing `/workspace/personaplex.env`. **In every new terminal, run
`source /workspace/personaplex.env` first.** That turns on the venv and points to the
weight cache.

---

## 4. Load the runtime prompt from `prompts/persona.md`

Only the **"## Runtime prompt"** section goes to the model. PersonaPlex was trained on
short prompts, and the prompt stays in its memory for the whole conversation. The rest
of the file (character sheet, variants) is notes for us.

Print it as one line:

```bash
python server/personaplex/runtime_prompt.py
```

How it reaches the model:

- **Live server:** the prompt is **not** a command-line flag. The browser sends it as the
  `text_prompt` parameter (plus `voice_prompt`) when it opens the `/api/chat` WebSocket.
  In the web UI, you paste it into the prompt field. In Phase 2, our LiveKit agent will
  call `load_runtime_prompt()` from `runtime_prompt.py` and send it automatically.
- **Offline test:** pass it with `--text-prompt "$(python server/personaplex/runtime_prompt.py)"` (see below).

When you edit `prompts/persona.md`, start a new conversation to pick up the change.
There's no need to restart the server.

---

## 5. Test a voice conversation

### Test A: offline (no browser, proves the model works)

This feeds a recorded question from PersonaPlex's repo through Lumi and writes her
reply to a WAV file:

```bash
source /workspace/personaplex.env
cd /workspace/personaplex
python -m moshi.offline \
  --voice-prompt "NATF2.pt" \
  --text-prompt "$(python /workspace/persona-live/server/personaplex/runtime_prompt.py)" \
  --input-wav "assets/test/input_assistant.wav" \
  --seed 42424242 \
  --output-wav "/workspace/lumi_test.wav" \
  --output-text "/workspace/lumi_test.json"
```

- Output: `lumi_test.wav` is the same length as the input. Lumi's speech is placed where she'd naturally talk. `lumi_test.json` holds the text she said.
- Listen: download the WAV through RunPod's Jupyter file browser, or `runpodctl send /workspace/lumi_test.wav`. It's small, a few hundred KB.
- Voice presets: `NATF0–3` / `NATM0–3` (natural female/male) and `VARF0–4` / `VARM0–4` (variety).

### Test B: live conversation in your browser

```bash
source /workspace/personaplex.env
cd /workspace/personaplex
python -m moshi.server --host 0.0.0.0 --port 8998
```

- `--host 0.0.0.0` makes the server reachable from outside the container. The default `localhost` isn't.
- Wait for `Access the Web UI directly at …` in the log. The first start loads the weights into VRAM, which takes about a minute.
- On your Mac, open **`https://<POD_ID>-8998.proxy.runpod.net`**. The pod ID is in the RunPod dashboard.
- In the UI: pick a voice (e.g. `NATF2`), paste the runtime prompt, allow the mic, and talk. **Use headphones**, or Lumi will hear herself through your speakers.

**Things to check:**

- [ ] She answers in character as Lumi and says she's an AI if you ask "are you human?"
- [ ] She backchannels ("mm", "oh nice") while you talk
- [ ] **Barge-in:** start talking while she's mid-sentence. She should stop and listen
- [ ] Replies start quickly (under about a second) and don't stutter

**Why no `--ssl`?** Browsers only allow the mic on HTTPS pages or `localhost`. The
RunPod proxy already gives you HTTPS, so the server itself runs plain HTTP behind it.
The README's `--ssl "$SSL_DIR"` is for when you connect to the server directly without
a proxy. That uses a self-signed certificate, so your browser will show a warning.

**If the proxy URL doesn't work (e.g. the WebSocket drops),** use an SSH tunnel
instead. RunPod shows the SSH command under **Connect**:

```bash
# on your Mac — forwards your localhost:8998 to the pod
ssh -L 8998:localhost:8998 root@<pod-ip> -p <ssh-port> -i ~/.ssh/id_ed25519
```

Then open **<http://localhost:8998>**. Browsers allow the mic on `localhost`.

⚠️ The proxy URL is public: anyone who has it can talk to your GPU. Don't share it, and stop the pod when you're done.

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `CUDA out of memory` | Add `--cpu-offload` to the command (slower), or rent a 48 GB card |
| `access denied` / 401 / 403 downloading weights | Accept the license on the model page with the **same** HF account as your token |
| Voice is choppy/robotic | The GPU is too slow for real time. Try an L40S / A100 / H100 |
| Lumi drifts out of character in long chats | Expected: memory is a ~2.5-minute sliding window, though the system prompt stays pinned. Keep the runtime prompt short and clear |
| `No space left on device` | Make the `/workspace` volume larger (60 GB+) |
| New terminal: `python: No module named moshi` | Run `source /workspace/personaplex.env` |

---

## Custom voice (`voices/lumi.wav`)

The server accepts non-`.pt` voice files from its voice directory
(`--voice-prompt-dir`). We haven't confirmed the required format (length, sample rate)
yet, so we're using presets for Phase 1. Whatever voice you use must be **original or
properly licensed**. Never clone a real person's voice without their written consent.
Voice files are gitignored.
