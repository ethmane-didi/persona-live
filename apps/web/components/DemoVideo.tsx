"use client";

import { useEffect, useRef } from "react";

/**
 * A generated test pattern that stands in for Lumi's video while there's no
 * face model running (no GPU). It's drawn locally on a canvas and never sent
 * anywhere; it only lets you check the video-call layout.
 */
export function DemoVideo({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let frame = 0;
    let raf = 0;
    const start = performance.now();

    const draw = () => {
      const { width: w, height: h } = canvas;
      const t = (performance.now() - start) / 1000;

      // Slowly shifting background.
      const hue = (t * 12) % 360;
      const bg = ctx.createLinearGradient(0, 0, w, h);
      bg.addColorStop(0, `hsl(${hue} 45% 18%)`);
      bg.addColorStop(1, `hsl(${(hue + 60) % 360} 45% 10%)`);
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      // Moving bar: shows the "video" is live and how smooth it is.
      const barX = ((t * 0.25) % 1) * w;
      ctx.fillStyle = "rgb(255 255 255 / 0.12)";
      ctx.fillRect(barX - 20, 0, 40, h);

      // A soft "face" placeholder so the framing reads like a video call.
      ctx.fillStyle = "rgb(255 255 255 / 0.08)";
      ctx.beginPath();
      ctx.ellipse(w / 2, h * 0.46, w * 0.16, h * 0.28, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgb(255 255 255 / 0.85)";
      ctx.font = `600 ${Math.round(h * 0.06)}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText("Demo video: not Lumi", w / 2, h * 0.9);
      ctx.font = `${Math.round(h * 0.035)}px ui-monospace, monospace`;
      ctx.fillStyle = "rgb(255 255 255 / 0.55)";
      ctx.fillText(`frame ${frame} · ${t.toFixed(1)} s`, w / 2, h * 0.96);

      frame += 1;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={canvasRef} width={960} height={540} className={className} aria-label="Demo test pattern" />;
}
