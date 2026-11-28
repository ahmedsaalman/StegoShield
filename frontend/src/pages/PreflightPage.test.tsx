import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../state/AppState";
import { PreflightPage } from "./PreflightPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <AppStateProvider>
        <PreflightPage />
      </AppStateProvider>
    </MemoryRouter>,
  );
}

const CAPACITY = { width: 64, height: 64, channels: 3, is_lossy_source: false, max_message_bytes: { password: 1500, public_key: 1484 } };

function fakeServer(url: string, init?: RequestInit): Promise<Response> {
  const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body)));
  if (url === "/api/capacity") return json(CAPACITY);
  if (url === "/api/preflight") {
    const form = init?.body as FormData;
    return json({
      capacity: CAPACITY,
      message_bytes: Number(form.get("message_bytes")),
      method: form.get("method"),
      fits: true,
      payload_percent: 33,
      recommended_max_message_bytes: 600,
      risk: { probability: 0.18, level: "low", method: "detector-in-the-loop" },
      recommendation: "Fine as planned.",
      texture: "textured",
    });
  }
  return Promise.resolve(new Response("{}", { status: 404 }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(fakeServer));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:test", revokeObjectURL: () => undefined }));
});

afterEach(() => vi.unstubAllGlobals());

describe("PreflightPage", () => {
  it("lets the message size be cleared and retyped", async () => {
    const user = userEvent.setup();
    renderPage();
    const size = screen.getByLabelText("Message size in bytes");

    await user.clear(size);
    expect(size).toHaveValue(null);
    await user.type(size, "2000");

    expect(size).toHaveValue(2000);
  });

  it("says when the result no longer matches the form", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.upload(screen.getByLabelText(/Drop an image here/), new File(["png"], "cover.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Run pre-flight check" }));
    expect(await screen.findByText("Result for 500 bytes")).toBeInTheDocument();
    expect(screen.queryByText("The form has changed since this check")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Message size in bytes"), "0");

    expect(screen.getByText("The form has changed since this check")).toBeInTheDocument();
  });
});
