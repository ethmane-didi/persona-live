# server/face: Lumi's photoreal face (MuseTalk 1.5)

Turns Lumi's voice into a lip-synced video of her, live. MuseTalk re-draws only the
mouth area on a **looping video** of the persona, so blinks, small head movements and
"listening" come from the real footage.

```text
agent ──ws://127.0.0.1:8999/stream──▶ service.py ──▶ musetalk_stream.py (Whisper features → UNet → VAE → blend)
      ◀── one I420 video frame per 40 ms of audio ──┘
```

| File | What it does |
|---|---|
| `musetalk_stream.py` | Streaming version of MuseTalk's real-time path: rolling audio buffer, Whisper features, per-frame windows exactly like MuseTalk's `get_whisper_chunk`, UNet + VAE, pasted onto the idle loop |
| `service.py` | Localhost WebSocket the agent connects to (protocol in its docstring). One conversation at a time |
| `prepare_avatar.sh` | Runs MuseTalk's own avatar preparation on the likeness video (once) |
| `../scripts/face-setup.sh` | Installs MuseTalk (Python 3.10 venv at `/root/venvs/face`) and the inference weights from official sources |

**Status: written, not yet run.** Everything here gets its first test in the next GPU session.

## Timing and sync

- MuseTalk renders at 25 fps. Each frame (40 ms) uses audio from 80 ms before to 80 ms after it, so a frame can only be drawn ~80 ms after its audio arrives.
- Frames render in batches of 5 (200 ms; `--batch-frames`). Expected lag from audio in to frame out: about **280 ms plus compute**.
- The agent holds Lumi's voice back until its frame exists and publishes each frame with exactly its 40 ms of audio (LiveKit `AVSynchronizer`), so lips and voice stay in sync. **The cost:** she starts speaking, and reacts to interruptions, that much later. Smaller batches cut the lag but cost more GPU time per frame.
- Real time needs under **40 ms of render time per frame**. The service logs it every 10 s: `render X ms/frame (Y x real time)`.

## Likeness video (you provide it)

Original or licensed, with a **signed release** covering AI/synthetic use, commercial use
and modification. Never a real person without written consent.

- 20–30 s, frontal, steady camera, good even light, 720p or higher
- Mouth mostly closed, natural blinks, small natural head movement
- Any frame rate (`prepare_avatar.sh` converts to 25 fps); audio is ignored
- Put it on the pod at `/workspace/likeness/lumi.mp4` (gitignored; never commit it)

MuseTalk plays the loop forward and then backward, so it never jumps. Longer clips repeat less often.

## GPU session steps

```bash
cd /workspace/persona-live
bash server/scripts/face-setup.sh                 # ~10 min the first time
source /workspace/face.env
bash server/face/prepare_avatar.sh /workspace/likeness/lumi.mp4 lumi
cd server/face && python service.py --avatar lumi  # wait for "face service ready"
```

Then start the vision service, PersonaPlex and the agent (order in `server/agent/README.md`).

### What to measure

1. **Face alone:** render ms/frame with PersonaPlex idle. Needs < 40 ms.
2. **Face + PersonaPlex on the same GPU** during a real conversation:
   - face: still < 40 ms/frame?
   - PersonaPlex: the agent log's `mic` and `lumi` seconds still grow at the same rate?
   - If either falls behind, try `--batch-frames 8`, then a second GPU or an H100.
3. **Sync:** clap or say "pa-pa-pa" and watch her lips. Target < 100 ms drift.
4. **Delay:** the agent log's `face delay` (expected ~300 ms).

## Open items before any commercial launch

- [ ] **S3FD face detector:** code from [face-alignment](https://github.com/1adrianb/face-alignment) (BSD-3-Clause code); weights download at first use from `adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth`. Check the weights' license and training-data terms.
- [ ] **Face-parsing BiSeNet weights** (`79999_iter.pth`, from a Google Drive link in MuseTalk's `download_weights.sh`; the face-parsing.PyTorch model) and torchvision's ResNet-18. Check the weights' license and training-data terms.
- [ ] Re-check MuseTalk's other parts at launch: whisper-tiny (Apache 2.0), sd-vae-ft-mse (MIT), DWPose (Apache 2.0). These were checked on Hugging Face.
- [ ] Signed release for Lumi's likeness video.

Both detectors only run in `prepare_avatar.sh` (once per avatar), not live, so swapping
them later for permissively licensed ones only means re-preparing the avatar.

## Backup: Ditto

If MuseTalk can't keep real time next to PersonaPlex, benchmark
[Ditto](https://github.com/antgroup/ditto-talkinghead) (Apache 2.0 code and weights;
animates one photo; has a streaming pipeline). Before using it commercially, replace its
bundled InsightFace models (`insightface_det.onnx`, `landmark106.onnx`), which are
non-commercial.
