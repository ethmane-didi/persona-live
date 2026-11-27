#!/usr/bin/env bash
# =============================================================================
# prepare_avatar.sh: turn Lumi's likeness video into a MuseTalk avatar (once).
#
# Run ON THE GPU POD with the face env loaded:
#   source /workspace/face.env
#   bash server/face/prepare_avatar.sh /workspace/likeness/lumi.mp4 lumi
#
# The video must be an original or licensed likeness with a signed release.
# Best results: 20-30 s, frontal, good light, mouth mostly closed, natural blinks.
#
# This runs MuseTalk's own preparation (face detection, face parsing, VAE
# latents for every frame), so the face service only has to run the fast part
# live. Output: $MUSETALK_DIR/results/v15/avatars/<id>/ (persistent).
# =============================================================================
set -euo pipefail

VIDEO="${1:?usage: prepare_avatar.sh <video.mp4> [avatar_id]}"
AVATAR_ID="${2:-lumi}"
MUSETALK_DIR="${MUSETALK_DIR:-/workspace/MuseTalk}"
WORK_DIR="/workspace/face_avatars"

[[ "$(uname -s)" == "Linux" ]] || { echo "Run this on the GPU pod, not on your Mac." >&2; exit 1; }
[[ -f "$VIDEO" ]] || { echo "Video not found: $VIDEO" >&2; exit 1; }
command -v python >/dev/null && python -c "import mmpose" 2>/dev/null \
  || { echo "Load the face env first: source /workspace/face.env" >&2; exit 1; }
mkdir -p "$WORK_DIR"

# MuseTalk was trained on 25 fps video; convert so frame timing matches the audio.
VIDEO_25="$WORK_DIR/${AVATAR_ID}_25fps.mp4"
echo "==> Converting to 25 fps -> $VIDEO_25"
ffmpeg -y -v warning -i "$VIDEO" -r 25 -an -c:v libx264 -crf 16 -pix_fmt yuv420p "$VIDEO_25"

# MuseTalk's realtime script prepares the avatar and then renders the listed
# audio clips; we give it one of its own short test clips just to finish the run.
CONFIG="$WORK_DIR/${AVATAR_ID}.yaml"
cat > "$CONFIG" <<EOF
$AVATAR_ID:
  preparation: True
  bbox_shift: 0
  video_path: "$VIDEO_25"
  audio_clips:
    audio_0: "data/audio/eng.wav"
EOF

echo "==> Preparing avatar '$AVATAR_ID' (face detection + parsing + latents; a few minutes)"
cd "$MUSETALK_DIR"
# The script asks "re-create it? (y/n)" if the avatar exists; answer yes.
printf 'y\n' | python -m scripts.realtime_inference \
  --inference_config "$CONFIG" \
  --version v15 \
  --unet_model_path models/musetalkV15/unet.pth \
  --unet_config models/musetalkV15/musetalk.json \
  --fps 25 \
  --skip_save_images

OUT="$MUSETALK_DIR/results/v15/avatars/$AVATAR_ID"
[[ -f "$OUT/latents.pt" ]] || { echo "Preparation didn't produce $OUT/latents.pt; check the errors above." >&2; exit 1; }
echo
echo "Avatar ready: $OUT ($(ls "$OUT/full_imgs" | wc -l) frames in the idle loop)"
echo "Start the face service: cd $(dirname "$0") && python service.py --avatar $AVATAR_ID"
