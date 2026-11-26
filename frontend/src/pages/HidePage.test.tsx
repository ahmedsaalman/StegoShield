import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../state/AppState";
import { HidePage } from "./HidePage";

const META = {
  version: "test",
  limits: { max_upload_bytes: 10_000_000, max_image_pixels: 1_000_000, max_message_bytes: 1000, rate_limit_per_minute: 60 },
  detector: { available: true, model_type: "Calibrated Random Forest", trained_at: null, unavailable_reason: null },
};
const CAPACITY = { width: 64, height: 64, channels: 3, is_lossy_source: false, max_message_bytes: { password: 1500, public_key: 1484 } };

let hideRequests: FormData[] = [];

function fakeServer(url: string, init?: RequestInit): Promise<Response> {
  const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  if (url === "/api/meta") return json(META);
  if (url === "/api/capacity") return json(CAPACITY);
  if (url === "/api/hide") {
    hideRequests.push(init?.body as FormData);
    return Promise.resolve(
      new Response("png", {
        headers: { "Content-Type": "image/png", "Content-Disposition": 'attachment; filename="holiday.png"' },
      }),
    );
  }
  return Promise.resolve(new Response("{}", { status: 404 }));
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppStateProvider>
        <HidePage />
      </AppStateProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  hideRequests = [];
  vi.stubGlobal("fetch", vi.fn(fakeServer));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:test", revokeObjectURL: () => undefined }));
});

afterEach(() => vi.unstubAllGlobals());

describe("HidePage", () => {
  it("points out every missing field instead of submitting an empty form", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Hide message" }));

    expect(await screen.findByText("Choose an image to hide the message in.")).toBeInTheDocument();
    expect(screen.getByText("Write the message you want to hide.")).toBeInTheDocument();
    expect(screen.getByText("Enter a password.")).toBeInTheDocument();
    expect(hideRequests).toHaveLength(0);
  });

  it("hides a password-protected message and offers the result for download", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.upload(screen.getByLabelText(/Choose an image/), new File(["png"], "holiday.png", { type: "image/png" }));
    await screen.findByText("1.5 KB");
    await user.type(screen.getByLabelText("Secret message"), "meet at noon");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Hide message" }));

    expect(await screen.findByRole("heading", { name: "Your message is hidden" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download holiday.png" })).toBeInTheDocument();
    await waitFor(() => expect(hideRequests).toHaveLength(1));
    expect(hideRequests[0]?.get("method")).toBe("password");
    expect(hideRequests[0]?.get("algorithm")).toBe("matching");
    expect(hideRequests[0]?.has("recipient_public_key")).toBe(false);
  });
});
