import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../state/AppState";
import { RevealPage } from "./RevealPage";

const META = {
  version: "test",
  limits: { max_upload_bytes: 10_000_000, max_image_pixels: 1_000_000, max_message_bytes: 1000, rate_limit_per_minute: 60 },
  detector: { available: true, model_type: "Calibrated Random Forest", trained_at: null, unavailable_reason: null },
};
const EXAMPLE_KEYS = {
  public_key_base64: "RXhhbXBsZVB1YmxpY0tleUV4YW1wbGVQdWJsaWNLZXk=",
  public_key_pem: "-----BEGIN PUBLIC KEY-----\nexample\n-----END PUBLIC KEY-----\n",
  private_key_pem: "-----BEGIN PRIVATE KEY-----\nexample\n-----END PRIVATE KEY-----\n",
  fingerprint: "AAAA BBBB CCCC DDDD",
};

let revealRequests: FormData[] = [];
let isExampleUnavailable = false;

function fakeServer(url: string, init?: RequestInit): Promise<Response> {
  const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
  if (url === "/api/meta") return json(META);
  if (url === "/api/keys/example") {
    return isExampleUnavailable
      ? json({ error: { code: "internal_error", message: "Something went wrong." } }, 500)
      : json(EXAMPLE_KEYS);
  }
  if (url === "/api/reveal") {
    revealRequests.push(init?.body as FormData);
    return json({ message: "just testing", encoding: "utf-8", message_bytes: 12 });
  }
  return json({}, 404);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppStateProvider>
        <RevealPage />
      </AppStateProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  revealRequests = [];
  isExampleUnavailable = false;
  vi.stubGlobal("fetch", vi.fn(fakeServer));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:test", revokeObjectURL: () => undefined }));
});

afterEach(() => vi.unstubAllGlobals());

describe("RevealPage", () => {
  it("reveals with the example private key without choosing a file", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.upload(screen.getByLabelText(/Drop the image here/), new File(["png"], "holiday.png", { type: "image/png" }));
    await user.click(screen.getByRole("radio", { name: /My private key/ }));
    await user.click(screen.getByRole("button", { name: "Use the example private key" }));

    expect(await screen.findByText("Example private key (testing only)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use the example private key" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reveal message" }));

    expect(await screen.findByRole("region", { name: "Decrypted message" })).toBeInTheDocument();
    await waitFor(() => expect(revealRequests).toHaveLength(1));
    expect(revealRequests[0]?.get("method")).toBe("public_key");
    expect(revealRequests[0]?.get("private_key")).toBe(EXAMPLE_KEYS.private_key_pem);
  });

  it("shows an error if the example key can't be loaded", async () => {
    isExampleUnavailable = true;
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("radio", { name: /My private key/ }));
    await user.click(screen.getByRole("button", { name: "Use the example private key" }));

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
    expect(screen.queryByText("Example private key (testing only)")).not.toBeInTheDocument();
  });
});
