import type { LabOutcome, RiskLevel, Verdict } from "./api";

export type Tone = "success" | "info" | "warning" | "danger";
export type StatusIcon = "check" | "info" | "alert" | "x";

export interface StatusPresentation {
  label: string;
  tone: Tone;
  icon: StatusIcon;
  summary: string;
}

// Every status is shown as icon + words + number, never colour alone.
export const RISK_PRESENTATION: Record<RiskLevel, StatusPresentation> = {
  low: {
    label: "Low risk",
    tone: "success",
    icon: "check",
    summary: "A detector is unlikely to notice a message of this size in this image.",
  },
  medium: {
    label: "Medium risk",
    tone: "warning",
    icon: "alert",
    summary: "A detector may notice. A shorter message or a busier image lowers the risk.",
  },
  high: {
    label: "High risk",
    tone: "danger",
    icon: "x",
    summary: "A detector is likely to notice. Use a more detailed image or a much shorter message.",
  },
};

export const VERDICT_PRESENTATION: Record<Verdict, StatusPresentation> = {
  clean: {
    label: "No sign of hidden data",
    tone: "success",
    icon: "check",
    summary: "The image's statistics look like an ordinary photo.",
  },
  likely_clean: {
    label: "Probably no hidden data",
    tone: "info",
    icon: "info",
    summary: "A few statistics are slightly unusual, but not enough to flag the image.",
  },
  suspicious: {
    label: "Possibly hidden data",
    tone: "warning",
    icon: "alert",
    summary: "Several statistics look like those of images that carry hidden data.",
  },
  stego: {
    label: "Hidden data likely",
    tone: "danger",
    icon: "x",
    summary: "The image's statistics strongly match images that carry hidden data.",
  },
};

// "Failed safely" is the intended result of every attack and lossy transport: nothing leaked.
export const LAB_OUTCOME_PRESENTATION: Record<LabOutcome, StatusPresentation> = {
  recovered: {
    label: "Recovered",
    tone: "success",
    icon: "check",
    summary: "The message came back intact.",
  },
  failed_safely: {
    label: "Failed safely",
    tone: "info",
    icon: "info",
    summary: "Nothing was revealed: no partial message, no garbage, no crash.",
  },
  unsafe: {
    label: "Unsafe",
    tone: "danger",
    icon: "x",
    summary: "Something other than the message or a clean refusal came back. This should never happen.",
  },
};
