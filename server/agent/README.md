# server/agent: LiveKit agent

Joins the LiveKit room as a participant, then:

1. receives the user's mic audio and feeds it to PersonaPlex (full-duplex, barge-in supported),
2. publishes PersonaPlex's reply audio back into the room,
3. (phase 3) sends that audio through Audio2Face and streams blendshapes over the data channel.

The voice backend sits behind one interface, so the fallback pipeline
(faster-whisper → Ollama → Kokoro) can be swapped in if PersonaPlex is blocked.

- **Phase:** 2 (audio), 3 (blendshapes)
- **Run (GPU server):** `python main.py dev`
