import { type ReactNode, useId } from "react";

interface CardProps {
  title: string;
  /** Mono label above the title, e.g. "Step 01". */
  step?: string;
  description?: ReactNode;
  /** Grey bar along the bottom for hints, counters and actions. */
  footer?: ReactNode;
  children?: ReactNode;
  /** Announce changes inside the card (for result cards). */
  isLive?: boolean;
}

/** Bordered section with a header, body and optional footer bar. */
export function Card({ title, step, description, footer, children, isLive = false }: CardProps) {
  const titleId = useId();
  return (
    <section className="card" aria-labelledby={titleId} role={isLive ? "status" : undefined}>
      <div className="card__header">
        {step && <p className="card__step">{step}</p>}
        <h2 id={titleId} className="card__title">
          {title}
        </h2>
        {description && <p className="card__description">{description}</p>}
      </div>
      {children && <div className="card__body stack">{children}</div>}
      {footer && <div className="card__footer">{footer}</div>}
    </section>
  );
}
