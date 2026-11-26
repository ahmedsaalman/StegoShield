import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, NETWORK_ERROR_MESSAGE } from "./api";

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const cover = new File(["png"], "holiday.png", { type: "image/png" });

afterEach(() => vi.unstubAllGlobals());

describe("api error handling", () => {
  it("turns the server's error body into an ApiError with code, field and request id", async () => {
    mockFetch(
      jsonResponse(
        { error: { code: "capacity_exceeded", message: "Too long.", field: "message", request_id: "abc" } },
        422,
      ),
    );

    const error = await api.capacity(cover).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, code: "capacity_exceeded", field: "message", requestId: "abc" });
  });

  it("reports an unreachable server as a network error", async () => {
    mockFetch(new TypeError("Failed to fetch"));

    await expect(api.meta()).rejects.toMatchObject({ code: "network_error", message: NETWORK_ERROR_MESSAGE });
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    mockFetch(new Response("<html>Bad gateway</html>", { status: 502 }));

    await expect(api.meta()).rejects.toMatchObject({ status: 502, code: "http_error" });
  });
});

describe("api.hide", () => {
  it("sends only the fields for the chosen method and returns the file name", async () => {
    const fetchMock = mockFetch(
      // A string body: jsdom's Blob can't back a Node Response.
      new Response("png", { headers: { "Content-Disposition": 'attachment; filename="holiday.png"' } }),
    );

    const result = await api.hide({
      cover,
      message: "hi",
      protection: { method: "public_key", recipientPublicKey: "KEY" },
      algorithm: "matching",
      layout: "pseudorandom",
    });

    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get("recipient_public_key")).toBe("KEY");
    expect(form.has("password")).toBe(false);
    expect(result.filename).toBe("holiday.png");
  });
});
