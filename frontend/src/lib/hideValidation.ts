import type { KeyMethod } from "./api";
import { formatBytes } from "./format";

export const RECOMMENDED_PASSWORD_LENGTH = 12;

export interface HideFormInput {
  hasCover: boolean;
  messageBytes: number;
  /** Largest message the cover holds with the chosen method, once known. */
  capacityBytes: number | null;
  method: KeyMethod;
  password: string;
  confirmPassword: string;
  recipientKey: string;
  recipientKeyProblem: string | null;
}

export type HideField = "cover" | "message" | "password" | "confirmPassword" | "recipientKey";
export type HideFormErrors = Partial<Record<HideField, string>>;

/** Field order matches the page, so the first error is the first one the user reaches. */
export const HIDE_FIELD_ORDER: HideField[] = ["cover", "message", "password", "confirmPassword", "recipientKey"];

export function validateHideForm(input: HideFormInput): HideFormErrors {
  const errors: HideFormErrors = {};
  if (!input.hasCover) errors.cover = "Choose an image to hide the message in.";

  const messageError = validateMessage(input);
  if (messageError) errors.message = messageError;

  if (input.method === "password") {
    if (!input.password) errors.password = "Enter a password.";
    else if (input.confirmPassword !== input.password) errors.confirmPassword = "The passwords don't match.";
  } else if (!input.recipientKey.trim()) {
    errors.recipientKey = "Paste the recipient's public key.";
  } else if (input.recipientKeyProblem) {
    errors.recipientKey = input.recipientKeyProblem;
  }
  return errors;
}

export function firstInvalidField(errors: HideFormErrors): HideField | undefined {
  return HIDE_FIELD_ORDER.find((field) => errors[field]);
}

function validateMessage({ messageBytes, capacityBytes }: HideFormInput): string | null {
  if (messageBytes === 0) return "Write the message you want to hide.";
  if (capacityBytes !== null && messageBytes > capacityBytes) {
    return (
      `The message is ${formatBytes(messageBytes)} but this image holds at most ${formatBytes(capacityBytes)}. ` +
      "Shorten the message or use a larger image."
    );
  }
  return null;
}
