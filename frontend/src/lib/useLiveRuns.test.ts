import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { useLiveRuns } from "./useLiveRuns";

interface Pending {
  id: string;
  signal: AbortSignal;
  resolve: (value: string) => void;
  reject: (error: unknown) => void;
}

/** A runOne whose requests stay open until the test settles them. */
function controllableRunner() {
  const pending: Pending[] = [];
  const runOne = (id: string, signal: AbortSignal) =>
    new Promise<string>((resolve, reject) => pending.push({ id, signal, resolve, reject }));
  return { pending, runOne };
}

describe("useLiveRuns", () => {
  it("runs at most `concurrency` requests at once and fills in results as they finish", async () => {
    const { result } = renderHook(() => useLiveRuns<string>(2));
    const { pending, runOne } = controllableRunner();

    act(() => void result.current.start(["a", "b", "c"], runOne));

    expect(pending.map((p) => p.id)).toEqual(["a", "b"]);
    expect(result.current.isRunning).toBe(true);
    expect(result.current.states).toEqual({ a: { status: "running" }, b: { status: "running" }, c: { status: "waiting" } });

    await act(async () => pending[0]?.resolve("A"));
    expect(result.current.states.a).toEqual({ status: "done", result: "A" });
    expect(pending.map((p) => p.id)).toEqual(["a", "b", "c"]);

    await act(async () => {
      pending[1]?.reject(new ApiError(500, "boom", "Broke."));
      pending[2]?.resolve("C");
    });
    await waitFor(() => expect(result.current.isRunning).toBe(false));
    expect(result.current.states.b).toMatchObject({ status: "error" });
    expect(result.current.states.c).toEqual({ status: "done", result: "C" });
  });

  it("stop aborts what is in flight and puts it back to waiting", async () => {
    const { result } = renderHook(() => useLiveRuns<string>(1));
    const { pending, runOne } = controllableRunner();

    act(() => void result.current.start(["a", "b"], runOne));
    act(() => result.current.stop());

    expect(pending[0]?.signal.aborted).toBe(true);
    expect(result.current.isRunning).toBe(false);
    expect(result.current.states).toEqual({ a: { status: "waiting" }, b: { status: "waiting" } });

    await act(async () => pending[0]?.resolve("late"));
    expect(result.current.states.a).toEqual({ status: "waiting" });
    expect(pending).toHaveLength(1);
  });

  it("reset clears every state", () => {
    const { result } = renderHook(() => useLiveRuns<string>());
    const { runOne } = controllableRunner();

    act(() => void result.current.start(["a"], runOne));
    act(() => result.current.reset());

    expect(result.current.states).toEqual({});
  });

  it("unmounting aborts the run", () => {
    const { result, unmount } = renderHook(() => useLiveRuns<string>());
    const { pending, runOne } = controllableRunner();

    act(() => void result.current.start(["a"], runOne));
    unmount();

    expect(pending[0]?.signal.aborted).toBe(true);
  });
});
