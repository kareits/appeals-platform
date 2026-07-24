/**
 * Unit tests for the gateway API client: contract enforcement, error classification, correlation
 * diagnostics, Retry-After parsing, and cancellation.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";
import { ApiError, NetworkError, ProtocolError } from "./errors";
import { stubDeferredFetch, stubFetch } from "../test/utils";

interface Payload {
  value: string;
}

function makeClient(onUnauthorized = vi.fn()): {
  client: ApiClient;
  onUnauthorized: typeof onUnauthorized;
} {
  const client = new ApiClient({ getToken: () => "tok", onUnauthorized });
  return { client, onUnauthorized };
}

const identity = (raw: unknown): Payload => raw as Payload;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiClient.request", () => {
  it("returns the decoded body and sends auth and correlation headers", async () => {
    const fetchMock = stubFetch([{ status: 200, json: { value: "ok" } }]);
    const { client } = makeClient();

    const result = await client.request<Payload>("/x", { decode: identity });

    expect(result).toEqual({ value: "ok" });
    const headers = fetchMock.mock.calls[0]![1]!.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok");
    expect(headers["X-Correlation-ID"]).toBeTruthy();
  });

  it("invokes the unauthorized handler and throws ApiError on 401", async () => {
    stubFetch([{ status: 401, json: { title: "Unauthorized", status: 401 } }]);
    const { client, onUnauthorized } = makeClient();

    await expect(client.request("/x", { decode: identity })).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not invoke the unauthorized handler on 403", async () => {
    stubFetch([{ status: 403, json: { title: "Forbidden", status: 403 } }]);
    const { client, onUnauthorized } = makeClient();

    await expect(client.request("/x", { decode: identity })).rejects.toMatchObject({ status: 403 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("captures the correlation id on an error", async () => {
    stubFetch([{ status: 500, json: { title: "Server", status: 500 }, correlationId: "cid-123" }]);
    const { client } = makeClient();

    await expect(client.request("/x", { decode: identity })).rejects.toMatchObject({
      correlationId: "cid-123",
    });
  });

  it("parses a bounded Retry-After on 429", async () => {
    stubFetch([{ status: 429, json: { title: "Too Many", status: 429 }, retryAfter: "5" }]);
    const { client } = makeClient();

    await expect(client.request("/x", { decode: identity })).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 5,
    });
  });

  it("ignores an out-of-range Retry-After", async () => {
    stubFetch([{ status: 429, json: { title: "Too Many", status: 429 }, retryAfter: "999999" }]);
    const { client } = makeClient();

    await expect(client.request("/x", { decode: identity })).rejects.toMatchObject({
      retryAfterSeconds: null,
    });
  });

  it.each([502, 503, 504])("maps gateway status %s to ApiError", async (status) => {
    stubFetch([{ status, json: { title: "Gateway", status } }]);
    const { client } = makeClient();
    await expect(client.request("/x", { decode: identity })).rejects.toMatchObject({ status });
  });

  it("raises ProtocolError on invalid JSON", async () => {
    stubFetch([{ status: 200, invalidJson: true }]);
    const { client } = makeClient();
    await expect(client.request("/x", { decode: identity })).rejects.toBeInstanceOf(ProtocolError);
  });

  it("raises ProtocolError on an unexpected media type", async () => {
    stubFetch([{ status: 200, json: { value: "ok" }, contentType: "text/html" }]);
    const { client } = makeClient();
    await expect(client.request("/x", { decode: identity })).rejects.toBeInstanceOf(ProtocolError);
  });

  it("raises ProtocolError when the decoder rejects the shape", async () => {
    stubFetch([{ status: 200, json: { value: "ok" } }]);
    const { client } = makeClient();
    const failing = (): Payload => {
      throw new ProtocolError("bad shape");
    };
    await expect(client.request("/x", { decode: failing })).rejects.toBeInstanceOf(ProtocolError);
  });

  it("raises NetworkError when fetch rejects at the transport layer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const { client } = makeClient();
    await expect(client.request("/x", { decode: identity })).rejects.toBeInstanceOf(NetworkError);
  });

  it("re-raises the AbortError on caller cancellation (silent)", async () => {
    const calls = stubDeferredFetch();
    const { client, onUnauthorized } = makeClient();
    const controller = new AbortController();

    const promise = client.request("/x", { decode: identity, signal: controller.signal });
    // Wait a microtask so fetch is invoked and the abort listener is attached.
    await Promise.resolve();
    controller.abort();

    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
    expect(calls[0]!.signal).not.toBeNull();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("parses a problem under an exact application/problem+json media type (params and case)", async () => {
    stubFetch([
      {
        status: 400,
        json: { title: "Bad Request", status: 400 },
        contentType: "Application/Problem+JSON; charset=utf-8",
      },
    ]);
    const { client } = makeClient();
    const error = await client.request("/x", { decode: identity }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).problem).toMatchObject({ title: "Bad Request", status: 400 });
  });

  it.each(["application/json", "application/jsonp", "application/problem+jsonp", "text/html"])(
    "fails closed with ProtocolError when an error uses the non-problem media type %s",
    async (contentType) => {
      stubFetch([{ status: 400, json: { title: "Bad", status: 400 }, contentType }]);
      const { client } = makeClient();
      await expect(client.request("/x", { decode: identity })).rejects.toBeInstanceOf(
        ProtocolError,
      );
    },
  );

  it("surfaces the status of a bodyless error with no problem", async () => {
    stubFetch([{ status: 503, json: undefined, contentType: null }]);
    const { client } = makeClient();
    const error = await client.request("/x", { decode: identity }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).problem).toBeNull();
  });

  it("accepts application/json with a charset parameter and mixed case", async () => {
    stubFetch([
      { status: 200, json: { value: "ok" }, contentType: "Application/JSON; charset=utf-8" },
    ]);
    const { client } = makeClient();
    await expect(client.request<Payload>("/x", { decode: identity })).resolves.toEqual({
      value: "ok",
    });
  });

  it.each(["application/jsonp", "text/application/json", "application/json-patch+json"])(
    "rejects the near-match media type %s",
    async (contentType) => {
      stubFetch([{ status: 200, json: { value: "ok" }, contentType }]);
      const { client } = makeClient();
      await expect(client.request("/x", { decode: identity })).rejects.toBeInstanceOf(
        ProtocolError,
      );
    },
  );

  it("keeps a well-formed correlation id but drops a malformed or oversized one", async () => {
    stubFetch([{ status: 500, json: { title: "Server", status: 500 }, correlationId: "cid_ok-1" }]);
    const first = makeClient();
    await expect(first.client.request("/x", { decode: identity })).rejects.toMatchObject({
      correlationId: "cid_ok-1",
    });

    stubFetch([
      { status: 500, json: { title: "Server", status: 500 }, correlationId: "bad id with spaces" },
    ]);
    const second = makeClient();
    await expect(second.client.request("/x", { decode: identity })).rejects.toMatchObject({
      correlationId: null,
    });

    stubFetch([
      { status: 500, json: { title: "Server", status: 500 }, correlationId: "a".repeat(200) },
    ]);
    const third = makeClient();
    await expect(third.client.request("/x", { decode: identity })).rejects.toMatchObject({
      correlationId: null,
    });
  });
});
