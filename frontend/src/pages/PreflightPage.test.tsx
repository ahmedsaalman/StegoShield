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

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 404 }))));
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
});
