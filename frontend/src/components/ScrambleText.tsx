import { useEffect, useState } from "react";

import { prefersReducedMotion } from "../lib/motion";

const GLYPHS = "ABCDEF0123456789abcdef#%&*+=?";
const MAX_ANIMATED_LENGTH = 800;

interface ScrambleTextProps {
  text: string;
  durationMs?: number;
}

/**
 * "Decrypts" text on screen: scrambled glyphs settle left to right into the real text.
 * The animated copy is hidden from screen readers, which get the real text at once.
 * Long texts and reduced-motion users skip the effect.
 */
export function ScrambleText({ text, durationMs = 900 }: ScrambleTextProps) {
  const [shown, setShown] = useState("");

  useEffect(() => {
    const isInstant = prefersReducedMotion() || text.length > MAX_ANIMATED_LENGTH;
    const startedAt = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = isInstant ? 1 : Math.min(1, (now - startedAt) / durationMs);
      setShown(scramble(text, Math.floor(progress * text.length)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text, durationMs]);

  return (
    <>
      <span aria-hidden="true">{shown}</span>
      <span className="visually-hidden">{text}</span>
    </>
  );
}

function scramble(text: string, resolvedCount: number): string {
  let result = text.slice(0, resolvedCount);
  for (let index = resolvedCount; index < text.length; index++) {
    const char = text[index] ?? "";
    result += /\s/.test(char) ? char : (GLYPHS[Math.floor(Math.random() * GLYPHS.length)] ?? char);
  }
  return result;
}
