import type { ReactNode } from "react";

import type { StatusIcon, Tone } from "../lib/presentation";
import { Icon } from "./Icon";

const TONE_ICONS: Record<Tone, StatusIcon> = { success: "check", info: "info", warning: "alert", danger: "x" };

interface AlertProps {
  tone: Tone;
  title?: string;
  children?: ReactNode;
  /** Errors interrupt screen readers; everything else waits politely. */
  live?: boolean;
  action?: ReactNode;
}

export function Alert({ tone, title, children, live = false, action }: AlertProps) {
  const role = live ? (tone === "danger" ? "alert" : "status") : undefined;
  return (
    <div className={`alert alert--${tone}`} role={role}>
      <Icon name={TONE_ICONS[tone]} className="alert__icon" />
      <div className="alert__body">
        {title && <p className="alert__title">{title}</p>}
        {children && <div className="alert__content">{children}</div>}
        {action && <div className="alert__action">{action}</div>}
      </div>
    </div>
  );
}
