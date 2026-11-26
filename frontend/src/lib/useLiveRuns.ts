import { useCallback, useEffect, useRef, useState } from "react";

import { type ApiError, isAbortError, toApiError } from "./api";

export type LiveRunState<T> =
  | { status: "waiting" }
  | { status: "running" }
  | { status: "done"; result: T }
  | { status: "error"; error: ApiError };

export interface LiveRuns<T> {
  states: Record<string, LiveRunState<T>>;
  isRunning: boolean;
  start: (ids: string[], runOne: (id: string, signal: AbortSignal) => Promise<T>) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/**
 * Runs one request per id, `concurrency` at a time, and keeps a live state per id so the page can
 * fill in results as they arrive. Starting again, stopping or unmounting aborts what is in flight.
 */
export function useLiveRuns<T>(concurrency = 2): LiveRuns<T> {
  const [states, setStates] = useState<Record<string, LiveRunState<T>>>({});
  const [isRunning, setIsRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const update = useCallback((id: string, state: LiveRunState<T>) => {
    setStates((previous) => ({ ...previous, [id]: state }));
  }, []);

  const start = useCallback(
    async (ids: string[], runOne: (id: string, signal: AbortSignal) => Promise<T>) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setStates(Object.fromEntries(ids.map((id) => [id, { status: "waiting" } as LiveRunState<T>])));
      setIsRunning(true);

      let next = 0;
      const worker = async () => {
        while (next < ids.length && !controller.signal.aborted) {
          const id = ids[next++];
          if (id === undefined) return;
          update(id, { status: "running" });
          try {
            const result = await runOne(id, controller.signal);
            if (!controller.signal.aborted) update(id, { status: "done", result });
          } catch (error) {
            if (controller.signal.aborted || isAbortError(error)) return;
            update(id, { status: "error", error: toApiError(error) });
          }
        }
      };
      await Promise.all(Array.from({ length: concurrency }, worker));
      if (controllerRef.current === controller) setIsRunning(false);
    },
    [concurrency, update],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsRunning(false);
    setStates((previous) =>
      Object.fromEntries(
        Object.entries(previous).map(([id, state]) => [id, state.status === "running" ? { status: "waiting" } : state]),
      ),
    );
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsRunning(false);
    setStates({});
  }, []);

  return { states, isRunning, start, stop, reset };
}
