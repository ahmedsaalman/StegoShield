import type { StatusPresentation } from "../lib/presentation";
import { Icon } from "./Icon";

interface StatusBadgeProps {
  status: StatusPresentation;
  /** Shown after the label, e.g. "18%". */
  value?: string;
  size?: "md" | "lg";
}

/** Icon + words + number in one badge, so the status never depends on colour alone. */
export function StatusBadge({ status, value, size = "md" }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-badge--${status.tone} status-badge--${size}`}>
      <Icon name={status.icon} size={size === "lg" ? 22 : 16} />
      <span>{status.label}</span>
      {value && (
        <>
          <span aria-hidden="true">·</span>
          <span className="status-badge__value">{value}</span>
        </>
      )}
    </span>
  );
}
