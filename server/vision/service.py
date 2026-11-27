"""Vision service: describes one camera frame in a sentence, for Lumi's role prompt.

PersonaPlex only takes text once (the role prompt, at the start of a conversation),
so the agent grabs one frame from the user's camera when they join, sends it here,
and adds the description to the prompt. Lumi can then greet the user and refer to
what she "saw". She can't notice changes later in the call.

    POST http://127.0.0.1:8997/describe?width=W&height=H
    body: raw RGB24 pixels (W*H*3 bytes)
    -> {"description": "..."}

Model: SmolVLM2-2.2B-Instruct (Apache-2.0) by default; set VISION_MODEL to swap.
Runs on the GPU pod in its own venv (see server/vision/README.md):
    python service.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import torch
from aiohttp import web
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

logger = logging.getLogger("vision-service")

MODEL_ID = os.getenv("VISION_MODEL", "HuggingFaceTB/SmolVLM2-2.2B-Instruct")

# Keep what reaches the role prompt neutral: what's visible, not who they are.
PROMPT = (
    "This is one frame from a person's webcam at the start of a video call. "
    "In one short sentence, describe what is visible: their clothing, hair, expression, "
    "anything they are holding, and the setting. Do not guess age, ethnicity, gender, "
    "health, body shape or any other personal or sensitive trait. "
    "If no person is visible, say what you see instead."
)
MAX_PIXELS = 1_000_000  # downscale bigger frames; the model doesn't need more


class Describer:
    def __init__(self, model_id: str) -> None:
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForImageTextToText.from_pretrained(model_id, torch_dtype=torch.bfloat16).to("cuda")
        self.model.eval()

    @torch.no_grad()
    def describe(self, image: Image.Image) -> str:
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
        prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self.processor(text=prompt, images=[image], return_tensors="pt").to("cuda", torch.bfloat16)
        output = self.model.generate(**inputs, max_new_tokens=60, do_sample=False)
        new_tokens = output[0, inputs["input_ids"].shape[1]:]
        text = self.processor.decode(new_tokens, skip_special_tokens=True).strip()
        return text.removeprefix("Assistant:").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Camera-frame describer for the LiveKit agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8997)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    logger.info("loading %s", MODEL_ID)
    describer = Describer(MODEL_ID)
    executor = ThreadPoolExecutor(max_workers=1)

    async def handle_describe(request: web.Request) -> web.Response:
        try:
            width, height = int(request.query["width"]), int(request.query["height"])
        except (KeyError, ValueError):
            return web.json_response({"error": "width and height query parameters are required"}, status=400)
        body = await request.read()
        if len(body) != width * height * 3:
            return web.json_response({"error": f"expected {width * height * 3} bytes of RGB24"}, status=400)
        image = Image.frombytes("RGB", (width, height), body)
        if width * height > MAX_PIXELS:
            scale = (MAX_PIXELS / (width * height)) ** 0.5
            image = image.resize((int(width * scale), int(height * scale)))
        t0 = time.perf_counter()
        description = await asyncio.get_running_loop().run_in_executor(executor, describer.describe, image)
        logger.info("described a %dx%d frame in %.2f s: %s", width, height, time.perf_counter() - t0, description)
        return web.json_response({"description": description})

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_post("/describe", handle_describe)
    logger.info("vision service ready on http://%s:%d/describe", args.host, args.port)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
