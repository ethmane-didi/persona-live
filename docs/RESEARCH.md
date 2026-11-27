# Building an Emma-style AI video persona for free

*Nov 26, 2026 · Ousman*

> **Update, Nov 27, 2026:** Phase 3 switched from Audio2Face to **MuseTalk 1.5**
> because Lumi needs a photoreal face, like a real person on a video call. Audio2Face
> only drives a 3D character with blendshapes (see "One catch" below). MuseTalk
> lip-syncs a looping video of an original or licensed likeness instead. The Audio2Face
> notes below are kept as background.

Partly possible. Every piece of software can be free and open, but running it isn't. This needs a real NVIDIA GPU, and an 8GB Mac can't run it. The usual "free" route is free code plus cheap or free GPU time.

## Nuance Labs: not open source

There are no public open weights for Nuplex, the model behind Emma. Nuance's public way in is the paid Nuplex Beta API (Nuance Live, at platform.nuancelabs.ai), so it can't be the free option.

## NVIDIA: the closest free stack

### The voice brain: PersonaPlex

This is the open model closest to what makes Emma feel natural. PersonaPlex is a real-time, full-duplex speech-to-speech model: you control its persona with a text role prompt and its voice with an audio sample. It listens and speaks at the same time, and it learned when to pause, when to interrupt and when to say "uh-huh."

- **License:** the code is MIT and the weights use the NVIDIA Open Model License. Commercial use is allowed, and NVIDIA claims no rights to the outputs.
- **Size:** built on Kyutai's Moshi. It's a 7B model, so plan on a rented GPU with plenty of VRAM.

### The face: Audio2Face

NVIDIA open-sourced the Audio2Face models, the SDK and the training framework, so you can fine-tune them. The release also includes Audio2Emotion models, which infer emotional state from audio in real time.

> **One catch:** Audio2Face animates a **3D character** using facial blendshapes. It doesn't produce photoreal video. You'd render the face in the browser with three.js or Unreal. That gives you a stylised Emma, not a lifelike one.

### For a photoreal face instead

Open lip-sync models like MuseTalk, LivePortrait or Ditto can animate a photo from audio. Quality and speed vary, and some have non-commercial licenses, so check each one before you build a product on it.

### Plumbing (free)

LiveKit or Pipecat, both open source and self-hostable, to stream audio and video between the browser and your GPU server. Frontend: Next.js, Tailwind, Supabase.

### If you'd rather use a turn-based pipeline than PersonaPlex

- **Speech-to-text:** NVIDIA Nemotron 3.5 Transcribe (free weights, commercial use allowed) or faster-whisper
- **LLM:** through Ollama (Qwen, Llama, Nemotron Nano)
- **Text-to-speech:** Kokoro or Piper

## Where the GPU comes from

| Option | Cost | Good for |
|---|---|---|
| Google Colab / Kaggle free GPUs | $0 | Testing that the models run. Sessions time out, so they can't serve users |
| Hugging Face Spaces | Free tier / cheap | Public demos |
| RunPod / Vast.ai rented GPU | Pay per hour, only while it's on | Real development and an early beta |
| Your own RTX 3090/4090 PC | One-off purchase | Unlimited local dev |

## Suggested path

1. Run the PersonaPlex demo on a rented GPU and talk to it with a custom role prompt. That alone gets you "Emma's voice."
2. Feed its audio output into Audio2Face and show the face in a three.js page.
3. Wrap it in LiveKit + Next.js with login, then add a cap on minutes per user, since every live minute uses GPU time.

You'll get Emma-like timing for close to zero cost while you prototype. What you won't get for free is Nuance's photoreal face that reacts to *your* face.

## Sources

- [NVIDIA PersonaPlex on GitHub](https://github.com/NVIDIA/PersonaPlex)
- [PersonaPlex weights on Hugging Face](https://huggingface.co/nvidia/personaplex-7b-v1)
- [NVIDIA PersonaPlex research page](https://research.nvidia.com/labs/adlr/personaplex)
- [The Decoder: NVIDIA open-sources PersonaPlex](https://the-decoder.com/nvidia-open-sources-personaplex-a-voice-ai-that-listens-and-talks-at-the-same-time/)
- [tbreak: PersonaPlex licensing](https://tbreak.com/nvidia-personaplex-open-source-voice-ai/)
- [NVIDIA: Open Sources Audio2Face](https://developer.nvidia.com/blog/nvidia-open-sources-audio2face-animation-model)
- [Audio2Face-3D v3.0 on Hugging Face](https://huggingface.co/nvidia/Audio2Face-3D-v3.0)
- [Apidog: Nemotron 3.5 Transcribe for free](https://apidog.com/blog/nemotron-3-5-transcribe-free/)
- [OrcaRouter: Nuplex 1.0 and Emma](https://www.orcarouter.ai/blog/nuplex-1-0-emma-full-duplex-video-persona)
