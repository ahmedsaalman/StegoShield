import type { Tone } from "../lib/presentation";

interface MeterProps {
  label: string;
  /** 0–1 */
  value: number;
  valueText: string;
  tone?: Tone | "neutral";
  /** Optional reference line, 0–1, e.g. a decision threshold or a recommended limit. */
  marker?: { position: number; label: string };
}

export function Meter({ label, value, valueText, tone = "neutral", marker }: MeterProps) {
  const percent = Math.min(100, Math.max(0, value * 100));
  return (
    <div className="meter">
      <div className="meter__header">
        <span className="meter__label">{label}</span>
        <span className="meter__value">{valueText}</span>
      </div>
      <div
        className="meter__track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
        aria-valuetext={valueText}
      >
        <div className={`meter__fill meter__fill--${tone}`} style={{ width: `${percent}%` }} />
        {marker && (
          <div className="meter__marker" style={{ left: `${Math.min(100, Math.max(0, marker.position * 100))}%` }} />
        )}
      </div>
      {marker && <p className="meter__marker-label">{marker.label}</p>}
    </div>
  );
}
