import type { ApiError } from "../lib/api";
import { Alert } from "./Alert";

const TITLES: Record<string, string> = {
  no_message_found: "No message found",
  capacity_exceeded: "The message doesn't fit",
  lossy_image: "This image can't hold a message any more",
  invalid_key: "Key not accepted",
  rate_limited: "Slow down a little",
  network_error: "Can't reach the server",
  detector_unavailable: "Detector not available",
  image_too_large: "Image too large",
  request_too_large: "Upload too large",
  unsupported_format: "Unsupported image format",
  invalid_image: "Unreadable image",
  lab_results_unavailable: "Saved results not available",
};

const NO_MESSAGE_CHECKLIST = [
  "Check the password, or that you chose the private key matching the public key the sender used.",
  "Use the original file you received. Images sent as photos through chat apps are usually recompressed.",
  "If the sender changed advanced options, match the layout they used.",
];

interface ErrorAlertProps {
  error: ApiError;
}

export function ErrorAlert({ error }: ErrorAlertProps) {
  return (
    <Alert tone="danger" title={TITLES[error.code] ?? "Something went wrong"} live>
      <p>{error.message}</p>
      {error.code === "no_message_found" && (
        <ul className="list">
          {NO_MESSAGE_CHECKLIST.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      )}
      {error.code === "internal_error" && error.requestId && (
        <p className="text-muted">
          If this keeps happening, report reference <code>{error.requestId}</code>.
        </p>
      )}
    </Alert>
  );
}
