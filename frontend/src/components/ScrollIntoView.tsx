import { type ReactNode, useEffect, useRef } from "react";

import { prefersReducedMotion } from "../lib/motion";

/**
 * Brings its content into view when it first appears. Results render below the form, which on a phone is
 * off screen, so without this a finished request can look like nothing happened.
 */
export function ScrollIntoView({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (typeof element?.scrollIntoView !== "function") return;
    element.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  }, []);

  return (
    <div ref={ref} className="scroll-target">
      {children}
    </div>
  );
}
