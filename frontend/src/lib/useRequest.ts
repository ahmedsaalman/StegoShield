import { useCallback, useEffect, useRef, useState } from "react";

import { type ApiError, isAbortError, toApiError } from "./api";

export type RequestState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: ApiError };

export interface Request<T> {
  state: RequestState<T>;
  run: (task: (signal: AbortSignal) => Promise<T>) => Promise<void>;
  reset: () => void;
}

/**
 * Tracks one async request. Starting a new request (or unmounting) aborts the previous one,
 * so a slow, stale response can never overwrite a newer result.
 */
export function useRequest<T>(): Request<T> {
  const [state, setState] = useState<RequestState<T>>({ status: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const run = useCallback(async (task: (signal: AbortSignal) => Promise<T>) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });
    try {
      const data = await task(controller.signal);
      if (!controller.signal.aborted) setState({ status: "success", data });
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) return;
      setState({ status: "error", error: toApiError(error) });
    }
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState({ status: "idle" });
  }, []);

  return { state, run, reset };
}
