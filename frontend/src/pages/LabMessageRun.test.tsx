import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LabMessageRun, payloadShare } from "./LabMessageRun";

const TEXTS = {
  texts: [
    { id: "note", title: "One-line note", description: "Tiny.", size_bytes: 75, text: "Meet at the north gate at 9." },
    { id: "dossier", title: "Long dossier", description: "Huge.", size_bytes: 40_196, text: "Section 1. Field notes." },
  ],
};
const CHECK_ROWS = [
  ["right_key", "Reveal with the right private key", "recovered"],
  ["wrong_key", "Reveal with someone else's private key", "failed_safely"],
  ["jpeg_q90", "Re-save as JPEG (quality 90), then reveal", "failed_safely"],
] as const;

function result(algorithm: "replacement" | "matching", actual: number, outcomes: string[] = []) {
  return {
    algorithm,
    predicted_probability: actual,
    predicted_level: actual > 0.65 ? "high" : "low",
    actual_probability: actual,
    is_detected: actual >= 0.72,
    psnr_db: 72.4,
    ssim: 0.99999,
    changed_values: 300,
    changed_pixels: 290,
    flat_area_share: 0.33,
    flat_change_share: 0.34,
    hotspot: { x: 96, y: 160, width: 64, height: 64 },
    checks: CHECK_ROWS.map(([check, label, expected], index) => ({
      check,
      label,
      expected,
      outcome: outcomes[index] ?? expected,
    })),
    top_signals: [
      { feature: "img_laplacian_var", z_score: 2.4 },
      { feature: "img_sobel_edge_energy", z_score: 0.3 },
    ],
    overview_image: "data:image/jpeg;base64,AAAA",
    hotspot_original: "data:image/png;base64,AAAA",
    hotspot_stego: "data:image/png;base64,AAAA",
  };
}

const runs: string[] = [];

function fakeServer(url: string, init?: RequestInit): Promise<Response> {
  const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  if (url === "/api/lab/messages") return json(TEXTS);
  const match = /^\/api\/lab\/messages\/([^/]+)\/run$/.exec(url);
  if (match?.[1]) {
    const id = match[1];
    runs.push(`${id}:${init?.body instanceof FormData ? (init.body.get("image") as File).name : "?"}`);
    const base = { text_id: id, title: id, threshold: 0.72, image_width: 512, image_height: 512 };
    if (id === "dossier") {
      return json({ ...base, message_bytes: 40_196, capacity_bytes: 1_000, fits: false, payload_percent: 100, results: [] });
    }
    return json({
      ...base,
      message_bytes: 75,
      capacity_bytes: 98_000,
      fits: true,
      payload_percent: 0.14,
      results: [result("replacement", 0.81, ["recovered", "recovered"]), result("matching", 0.22)],
    });
  }
  return Promise.resolve(new Response("{}", { status: 404 }));
}

const FILE = new File(["png"], "holiday.png", { type: "image/png" });
const SIZE = { width: 512, height: 512 };
// The replacement result reports a key that "recovered" the message when it should have failed: one unexpected check.

afterEach(() => {
  runs.length = 0;
  vi.unstubAllGlobals();
});

describe("payloadShare", () => {
  it("counts the public-key packet overhead against every colour value's lowest bit", () => {
    expect(payloadShare(75, SIZE)).toBeCloseTo((139 * 8) / (512 * 512 * 3));
    expect(payloadShare(98_240, SIZE)).toBe(1);
    expect(payloadShare(98_241, SIZE)).toBeGreaterThan(1);
  });
});

describe("LabMessageRun", () => {
  it("shows each sample message and how much of the user's image it would fill", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer));
    render(<LabMessageRun file={FILE} imageSize={{ width: 256, height: 256 }} canRun isDetectorMissing={false} />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("0.6%")).toBeInTheDocument();
    expect(within(table).getByText("doesn't fit")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "One-line note text" })).toHaveTextContent("Meet at the north gate");
  });

  it("hides every message in the user's image and explains where the changes landed", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer));
    const user = userEvent.setup();
    render(<LabMessageRun file={FILE} imageSize={SIZE} canRun isDetectorMissing={false} />);

    await user.click(await screen.findByRole("button", { name: "Run 2 messages in your image" }));

    const note = await screen.findByRole("status", { name: "One-line note result" });
    expect(await within(note).findByText("Why: LSB matching (±1)")).toBeInTheDocument();
    expect(within(note).getByText(/34% of those changes landed in the flattest third/)).toBeInTheDocument();
    expect(within(note).getByText(/Strongest signals: Fine texture \(Laplacian variance\), 2.4σ above/)).toBeInTheDocument();
    expect(within(note).queryByText(/Edge strength/)).not.toBeInTheDocument();
    expect(within(note).getByText("81% · flagged")).toBeInTheDocument();
    expect(within(note).getAllByText("Unexpected")).toHaveLength(1);
    expect(screen.getByRole("img", { name: /Your upload with One-line note hidden/ })).toBeInTheDocument();
    expect(screen.getByText("After: 64 × 64 px at (96, 160)")).toBeInTheDocument();

    const dossier = screen.getByRole("status", { name: "Long dossier result" });
    expect(await within(dossier).findByText("Doesn't fit in this image")).toBeInTheDocument();

    const summary = screen.getByRole("status", { name: "Message run summary" });
    expect(within(summary).getByText("1 of 1", { selector: "dd" })).toBeInTheDocument();
    expect(within(summary).getByText("5 of 6", { selector: "dd" })).toBeInTheDocument();
    expect(runs.sort()).toEqual(["dossier:holiday.png", "note:holiday.png"]);
  });

  it("switches the highlights to the other algorithm", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer));
    const user = userEvent.setup();
    render(<LabMessageRun file={FILE} imageSize={SIZE} canRun isDetectorMissing={false} />);

    await user.click(await screen.findByRole("button", { name: "Run 2 messages in your image" }));
    const note = await screen.findByRole("status", { name: "One-line note result" });
    await within(note).findByText("Why: LSB matching (±1)");
    await user.click(screen.getByRole("radio", { name: /LSB replacement/ }));

    expect(within(note).getByText("Why: LSB replacement")).toBeInTheDocument();
    expect(within(note).getByText(/To hide this safely, use a shorter message/)).toBeInTheDocument();
  });

  it("waits for an image and for the detector", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeServer));
    const { rerender } = render(<LabMessageRun file={null} imageSize={null} canRun={false} isDetectorMissing={false} />);

    expect(await screen.findByRole("button", { name: "Run 2 messages in your image" })).toBeDisabled();
    expect(screen.getAllByText("choose an image")).toHaveLength(2);

    rerender(<LabMessageRun file={FILE} imageSize={SIZE} canRun isDetectorMissing />);
    expect(screen.getByRole("button", { name: "Run 2 messages in your image" })).toBeDisabled();
    expect(screen.getByText(/messages can't be scored/)).toBeInTheDocument();
  });
});
