import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../state/AppState";
import { KeysPage } from "./KeysPage";

const EXAMPLE_KEYS = {
  public_key_base64: "RXhhbXBsZVB1YmxpY0tleUV4YW1wbGVQdWJsaWNLZXk=",
  public_key_pem: "-----BEGIN PUBLIC KEY-----\nexample\n-----END PUBLIC KEY-----\n",
  private_key_pem: "-----BEGIN PRIVATE KEY-----\nexample\n-----END PRIVATE KEY-----\n",
  fingerprint: "AAAA BBBB CCCC DDDD",
};

function fakeServer(url: string): Promise<Response> {
  const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
  if (url === "/api/keys/example") return json(EXAMPLE_KEYS);
  return json({}, 404);
}

beforeEach(() => vi.stubGlobal("fetch", vi.fn(fakeServer)));
afterEach(() => vi.unstubAllGlobals());

describe("KeysPage example key pair", () => {
  it("shows both example keys with a warning and can hand the public key to the Hide page", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AppStateProvider>
          <KeysPage />
        </AppStateProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "Show example keys" }));

    expect(await screen.findByText("Anyone can read messages hidden with this key")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Example public key" })).toHaveTextContent(EXAMPLE_KEYS.public_key_base64);
    expect(screen.getByRole("region", { name: "Example private key" })).toHaveTextContent("BEGIN PRIVATE KEY");
    expect(screen.getByRole("button", { name: "Download private key" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy public key" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Use for hiding messages" }));

    expect(screen.getByRole("button", { name: "In use for hiding" })).toBeDisabled();
    // The "Someone else's public key" card now lists it as the key in use, next to a Remove button.
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
    expect(screen.getAllByText(EXAMPLE_KEYS.fingerprint)).toHaveLength(2);
  });
});
