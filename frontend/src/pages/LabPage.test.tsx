import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../state/AppState";
import { LabPage } from "./LabPage";

const metaWith = (available: boolean) => ({
  version: "test",
  limits: { max_upload_bytes: 10_000_000, max_image_pixels: 16_777_216, max_message_bytes: 1000, rate_limit_per_minute: 60 },
  detector: { available, model_type: "Calibrated Random Forest", trained_at: null, unavailable_reason: null },
});

const RESULTS = {
  seed: 2026,
  held_out_covers: 417,
  detector: [{ algorithm: "replacement", layout: "pseudorandom", payload_percent: 5, roc_auc: 0.886 }],
  preflight_validity: [
    { texture: "all", predicted_level: "low", n_trials: 540, actual_detection_rate: 0 },
    { texture: "all", predicted_level: "high", n_trials: 2252, actual_detection_rate: 0.8806 },
  ],
  robustness: [
    { transport: "png_resave", label: "PNG re-save", n_trials: 40, recovered_rate: 1, failed_safely_rate: 0, unsafe_rate: 0 },
    { transport: "jpeg_q90", label: "JPEG q90", n_trials: 40, recovered_rate: 0, failed_safely_rate: 1, unsafe_rate: 0 },
  ],
  quality: [{ algorithm: "matching", payload_percent: 50, psnr_mean_db: 54.15, ssim_mean: 0.9982 }],
};

const DEMOS: Record<string, unknown> = {
  "/api/lab/quality": { points: [{ algorithm: "matching", payload_percent: 50, psnr_db: 54.2, ssim: 0.998 }] },
  "/api/lab/robustness": {
    message_bytes: 1024,
    trials: [
      { transport: "png_resave", label: "PNG re-save", outcome: "recovered" },
      { transport: "jpeg_q90", label: "JPEG q90", outcome: "failed_safely" },
    ],
  },
  "/api/lab/attacks": {
    trials: [{ attack: "wrong_password", description: "Reveal with the wrong password", outcome: "failed_safely" }],
  },
  "/api/lab/detector-comparison": {
    clean_probability: 0.23,
    threshold: 0.72,
    points: [
      { algorithm: "replacement", payload_percent: 10, probability: 0.98, is_detected: true },
      { algorithm: "matching", payload_percent: 10, probability: 0.45, is_detected: false },
    ],
  },
};

let calls: string[] = [];

function fakeServer(options: { detectorAvailable?: boolean; width?: number } = {}) {
  const { detectorAvailable = true, width = 512 } = options;
  return (url: string): Promise<Response> => {
    calls.push(url);
    const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    if (url === "/api/meta") return json(metaWith(detectorAvailable));
    if (url === "/api/lab/results") return json(RESULTS);
    if (url === "/api/capacity") {
      return json({ width, height: width, channels: 3, is_lossy_source: false, max_message_bytes: { password: 1, public_key: 1 } });
    }
    if (url in DEMOS) return json(DEMOS[url]);
    return Promise.resolve(new Response("{}", { status: 404 }));
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppStateProvider>
        <LabPage />
      </AppStateProvider>
    </MemoryRouter>,
  );
}

async function uploadCover(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByLabelText(/Drop an image/), new File(["png"], "cover.png", { type: "image/png" }));
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:test", revokeObjectURL: () => undefined }));
});

afterEach(() => vi.unstubAllGlobals());

describe("LabPage", () => {
  it("shows the saved held-out results without an upload", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer()));
    renderPage();

    expect(await screen.findByText("0% of 540")).toBeInTheDocument();
    expect(screen.getByText("88% of 2252")).toBeInTheDocument();
    expect(screen.getByText("0.886")).toBeInTheDocument();
    expect(screen.getByText("40 / 40")).toBeInTheDocument();
  });

  it("runs every demo and states each outcome in words", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer()));
    const user = userEvent.setup();
    renderPage();

    await uploadCover(user);
    await user.click(await screen.findByRole("button", { name: "Run all demos" }));

    const robustness = screen.getByRole("status", { name: "Transport robustness result" });
    expect(await within(robustness).findByText("Failed safely")).toBeInTheDocument();
    expect(within(robustness).getByText("Recovered")).toBeInTheDocument();
    const detector = screen.getByRole("status", { name: "Detector comparison result" });
    expect(await within(detector).findByText("98% · flagged")).toBeInTheDocument();
    expect(within(detector).getByText("45% · passes")).toBeInTheDocument();
    const quality = screen.getByRole("status", { name: "Visual quality result" });
    expect(await within(quality).findByText("54.2 dB")).toBeInTheDocument();
    expect(within(quality).getByText("SSIM 0.9980")).toBeInTheDocument();
    expect(calls).toContain("/api/lab/detector-comparison");
  });

  it("disables only the detector demo when no detector is installed", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer({ detectorAvailable: false })));
    const user = userEvent.setup();
    renderPage();

    await uploadCover(user);
    await user.click(await screen.findByRole("button", { name: "Run all demos" }));

    expect(await screen.findByText(/detector isn't installed/)).toBeInTheDocument();
    expect(await screen.findByText("Reveal with the wrong password")).toBeInTheDocument();
    expect(calls).not.toContain("/api/lab/detector-comparison");
  });

  it("blocks images over the 1-megapixel Lab limit", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer({ width: 2048 })));
    const user = userEvent.setup();
    renderPage();

    await uploadCover(user);

    expect(await screen.findByText("This image is too large for the Lab")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run all demos" })).toBeDisabled();
  });
});
