import type { ReactNode } from "react";

interface DisclosureProps {
  summary: string;
  children: ReactNode;
}

/** Native <details>: collapsible, keyboard-accessible, no JavaScript state. */
export function Disclosure({ summary, children }: DisclosureProps) {
  return (
    <details className="disclosure">
      <summary className="disclosure__summary">{summary}</summary>
      <div className="disclosure__content">{children}</div>
    </details>
  );
}
