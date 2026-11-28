import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../state/AppState";
import { Layout } from "./Layout";

const META = {
  version: "test",
  limits: { max_upload_bytes: 10_000_000, max_image_pixels: 1_000_000, max_message_bytes: 1000, rate_limit_per_minute: 60 },
  detector: { available: true, model_type: "Calibrated Random Forest", trained_at: null, unavailable_reason: null },
};

function renderLayout() {
  render(
    <MemoryRouter>
      <AppStateProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<h1>Overview</h1>} />
          </Route>
        </Routes>
      </AppStateProvider>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Layout footer", () => {
  it("shows that the detector is ready", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(META)))));
    renderLayout();

    expect(await screen.findByText("Detector ready")).toBeInTheDocument();
  });

  it("says so when the server can't be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    renderLayout();

    expect(await screen.findByText("Server unreachable")).toBeInTheDocument();
    expect(screen.queryByText("Detector ready")).not.toBeInTheDocument();
  });
});
