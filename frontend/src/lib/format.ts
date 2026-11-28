const KIBIBYTE = 1024;
const MEBIBYTE = 1024 * 1024;

const integerFormat = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const oneDecimalFormat = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });

export function formatBytes(bytes: number): string {
  if (bytes < KIBIBYTE) return `${integerFormat.format(bytes)} ${bytes === 1 ? "byte" : "bytes"}`;
  if (bytes < MEBIBYTE) return `${oneDecimalFormat.format(bytes / KIBIBYTE)} KB`;
  return `${oneDecimalFormat.format(bytes / MEBIBYTE)} MB`;
}

export function formatCount(value: number): string {
  return integerFormat.format(value);
}

/** Probability (0–1) as a whole-number percentage, e.g. 0.634 → "63%". */
export function formatProbability(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}

/** A value that is already a percentage, e.g. 4.036 → "4%" or "0.4%" when small. */
export function formatPercent(percent: number): string {
  return percent < 1 && percent > 0 ? `${oneDecimalFormat.format(percent)}%` : `${integerFormat.format(percent)}%`;
}

export function formatDimensions(width: number, height: number): string {
  return `${integerFormat.format(width)} × ${integerFormat.format(height)} px`;
}

/** A whole, positive number typed by the user, or null while the text isn't one yet (empty, "12.5", "-3"). */
export function parsePositiveInteger(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= 1 && Number.isSafeInteger(value) ? value : null;
}

export function utf8ByteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}
