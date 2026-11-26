// Typed client for the StegoShield API. Every failure surfaces as an ApiError with a
// stable `code` and a message that is safe to show to the user.

export type KeyMethod = "password" | "public_key";
export type EmbeddingAlgorithm = "replacement" | "matching";
export type EmbeddingLayout = "pseudorandom" | "sequential";
export type RiskLevel = "low" | "medium" | "high";
export type Verdict = "clean" | "likely_clean" | "suspicious" | "stego";

export interface DetectorStatus {
  available: boolean;
  model_type: string;
  trained_at: string | null;
  unavailable_reason: string | null;
}

export interface Meta {
  version: string;
  limits: {
    max_upload_bytes: number;
    max_image_pixels: number;
    max_message_bytes: number;
    rate_limit_per_minute: number;
  };
  detector: DetectorStatus;
}

export interface KeyPair {
  public_key_base64: string;
  public_key_pem: string;
  private_key_pem: string;
  fingerprint: string;
  is_private_key_encrypted: boolean;
}

export interface PublicKeyInfo {
  public_key_base64: string;
  fingerprint: string;
}

export interface Capacity {
  width: number;
  height: number;
  channels: number;
  is_lossy_source: boolean;
  max_message_bytes: Record<KeyMethod, number>;
}

export interface Preflight {
  capacity: Capacity;
  message_bytes: number;
  method: KeyMethod;
  fits: boolean;
  payload_percent: number;
  recommended_max_message_bytes: number;
  risk: { probability: number; level: RiskLevel; method: string };
  recommendation: string;
  texture: string;
}

export interface FeatureContribution {
  feature: string;
  value: number;
  typical_clean_value: number;
  z_score: number;
  contribution: number;
}

export interface Detection {
  probability: number;
  verdict: Verdict;
  is_stego: boolean;
  threshold: number;
  model_type: string;
  top_features: FeatureContribution[];
}

export interface RevealResult {
  message: string;
  encoding: "utf-8" | "base64";
  message_bytes: number;
}

export interface HiddenImage {
  blob: Blob;
  filename: string;
}

export type ProtectionSecret =
  | { method: "password"; password: string }
  | { method: "public_key"; recipientPublicKey: string };

export type UnlockSecret =
  | { method: "password"; password: string }
  | { method: "public_key"; privateKey: string; passphrase: string };

export interface HideRequest {
  cover: File;
  message: string;
  protection: ProtectionSecret;
  algorithm: EmbeddingAlgorithm;
  layout: EmbeddingLayout;
}

export interface RevealRequest {
  image: File;
  unlock: UnlockSecret;
  layout: EmbeddingLayout;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | undefined;
  readonly requestId: string | undefined;

  constructor(status: number, code: string, message: string, field?: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.field = field;
    this.requestId = requestId;
  }
}

export const NETWORK_ERROR_MESSAGE = "Can't reach the StegoShield server. Check your connection and try again.";
const DEFAULT_DOWNLOAD_NAME = "image.png";

type FormFields = Record<string, string | Blob | undefined>;

export const api = {
  meta: (signal?: AbortSignal) => getJson<Meta>("/meta", signal),

  generateKeyPair: (passphrase: string, signal?: AbortSignal) =>
    postJson<KeyPair>("/keys/generate", { passphrase: passphrase || null }, signal),

  inspectPublicKey: (publicKey: string, signal?: AbortSignal) =>
    postJson<PublicKeyInfo>("/keys/inspect", { public_key: publicKey.trim() }, signal),

  capacity: (image: File, signal?: AbortSignal) => postFormJson<Capacity>("/capacity", { image }, signal),

  preflight: (image: File, messageBytes: number, method: KeyMethod, signal?: AbortSignal) =>
    postFormJson<Preflight>("/preflight", { image, message_bytes: String(messageBytes), method }, signal),

  detect: (image: File, signal?: AbortSignal) => postFormJson<Detection>("/detect", { image }, signal),

  async hide(request: HideRequest, signal?: AbortSignal): Promise<HiddenImage> {
    const response = await send("/hide", { method: "POST", body: toFormData(hideFields(request)), signal });
    return { blob: await response.blob(), filename: filenameFrom(response.headers.get("Content-Disposition")) };
  },

  reveal: (request: RevealRequest, signal?: AbortSignal) =>
    postFormJson<RevealResult>("/reveal", revealFields(request), signal),
};

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "client_error", "Something went wrong in the browser. Please reload the page and try again.");
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function hideFields({ cover, message, protection, algorithm, layout }: HideRequest): FormFields {
  const secret =
    protection.method === "password"
      ? { password: protection.password }
      : { recipient_public_key: protection.recipientPublicKey };
  return { cover, message, method: protection.method, algorithm, layout, ...secret };
}

function revealFields({ image, unlock, layout }: RevealRequest): FormFields {
  const secret =
    unlock.method === "password"
      ? { password: unlock.password }
      : { private_key: unlock.privateKey, passphrase: unlock.passphrase };
  return { image, method: unlock.method, layout, ...secret };
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await send(path, { method: "GET", signal });
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await send(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return (await response.json()) as T;
}

async function postFormJson<T>(path: string, fields: FormFields, signal?: AbortSignal): Promise<T> {
  const response = await send(path, { method: "POST", body: toFormData(fields), signal });
  return (await response.json()) as T;
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, credentials: "same-origin" });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE);
  }
  if (!response.ok) throw await errorFromResponse(response);
  return response;
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code: string; message: string; field?: string; request_id?: string };
    };
    if (body.error) {
      const { code, message, field, request_id } = body.error;
      return new ApiError(response.status, code, message, field, request_id);
    }
  } catch {
    // Not JSON (e.g. a proxy error page): fall through to the generic message.
  }
  return new ApiError(response.status, "http_error", `The server returned an unexpected error (${response.status}).`);
}

function toFormData(fields: FormFields): FormData {
  const form = new FormData();
  for (const [name, value] of Object.entries(fields)) {
    if (value === undefined || value === "") continue;
    form.append(name, value);
  }
  return form;
}

function filenameFrom(contentDisposition: string | null): string {
  const match = contentDisposition?.match(/filename="([^"]+)"/);
  return match?.[1] ?? DEFAULT_DOWNLOAD_NAME;
}
