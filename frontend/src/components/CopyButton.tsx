import { useEffect, useState } from "react";

import { Button } from "./Button";

const CONFIRMATION_MS = 2000;

interface CopyButtonProps {
  text: string;
  label?: string;
}

export function CopyButton({ text, label = "Copy" }: CopyButtonProps) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (status === "idle") return;
    const timer = window.setTimeout(() => setStatus("idle"), CONFIRMATION_MS);
    return () => window.clearTimeout(timer);
  }, [status]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  }

  const buttonText = status === "copied" ? "Copied" : status === "failed" ? "Copy failed, select and copy" : label;
  return (
    <>
      <Button variant="secondary" icon={status === "copied" ? "check" : "copy"} onClick={copy}>
        {buttonText}
      </Button>
      <span className="visually-hidden" role="status">
        {status === "copied" ? "Copied to clipboard" : ""}
      </span>
    </>
  );
}
