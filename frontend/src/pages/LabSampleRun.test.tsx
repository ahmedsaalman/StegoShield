import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LabSampleRun, sampleMessageBytes } from "./LabSampleRun";

const SAMPLES = {
  source: "DIV2K (academic research use)",
  samples: [
    { id: "01-leaves", title: "Blurred leaves", texture: "smooth", texture_complexity: 52, image_url: "/api/lab/samples/01-leaves/image" },
    { id: "02-peacock", title: "Peacock feathers", texture: "textured", texture_complexity: 4434, image_url: "/api/lab/samples/02-peacock/image" },
  ],
};

function result(algorithm: "replacement" | "matching", actual: number, threshold = 0.72) {
  return {
    algorithm,
    predicted_probability: actual,
    predicted_level: actual > 0.65 ? "high" : actual < 0.35 ? "low" : "medium",
    actual_probability: actual,
    is_detected: actual >= threshold,
    psnr_db: 61.1,
    ssim: 0.9995,
    changed_values: 39_000,
    changed_share: 0.0496,
    stego_preview: "data:image/jpeg;base64,AAAA",
    change_map: "data:image/png;base64,AAAA",
  };
}

const runs: string[] = [];

function fakeServer(url: string, init?: RequestInit): Promise<Response> {
  const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  if (url === "/api/lab/samples") return json(SAMPLES);
  const match = /^\/api\/lab\/samples\/([^/]+)\/run$/.exec(url);
  if (match?.[1]) {
    runs.push(`${match[1]}:${JSON.parse(String(init?.body)).payload_percent}`);
    return json({
      sample_id: match[1],
      payload_percent: 10,
      message_bytes: 9766,
      threshold: 0.72,
      results: [result("replacement", 0.98), result("matching", 0.31)],
    });
  }
  return Promise.resolve(new Response("{}", { status: 404 }));
}

afterEach(() => {
  runs.length = 0;
  vi.unstubAllGlobals();
});

describe("sampleMessageBytes", () => {
  it("matches the server's size for a 512×512 photo in public-key mode", () => {
    expect(sampleMessageBytes(10)).toBe(9766);
    expect(sampleMessageBytes(1)).toBe(919);
  });
});

describe("LabSampleRun", () => {
  it("runs every built-in photo and reports what each one was exposed to", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer));
    const user = userEvent.setup();
    render(<LabSampleRun isDetectorMissing={false} />);

    await user.click(await screen.findByRole("button", { name: "Run on 2 photos" }));

    const peacock = await screen.findByRole("status", { name: "Peacock feathers result" });
    expect(await within(peacock).findByText("98% · flagged")).toBeInTheDocument();
    expect(within(peacock).getByText("31% · passes")).toBeInTheDocument();
    expect(await screen.findAllByText("Flagged with LSB replacement only")).toHaveLength(2);
    const summary = screen.getByRole("status", { name: "Sample run summary" });
    expect(within(summary).getByText("2 of 2", { selector: "dd" })).toBeInTheDocument();
    expect(within(summary).getByText("0 of 2", { selector: "dd" })).toBeInTheDocument();
    expect(runs.sort()).toEqual(["01-leaves:10", "02-peacock:10"]);
  });

  it("is disabled when no detector is installed", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer));
    render(<LabSampleRun isDetectorMissing />);

    expect(await screen.findByRole("button", { name: "Run on 2 photos" })).toBeDisabled();
    expect(screen.getByText(/sample run is unavailable/)).toBeInTheDocument();
  });
});
