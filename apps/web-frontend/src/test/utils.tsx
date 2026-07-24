/**
 * Test utilities: a provider wrapper and fetch stubs for component tests.
 *
 * `renderWithProviders` mounts a subtree inside the same global providers the app uses (TanStack
 * Query, the auth context, and a memory router) so components behave as they do at runtime.
 * `stubFetch` installs a `fetch` stub returning canned JSON responses (with realistic headers) so
 * tests exercise the real API client, decoders, and error handling without a network.
 * `stubDeferredFetch` returns controllable pending responses for race/isolation tests.
 */
import { type ReactElement, type ReactNode } from "react";
import { render, type RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";
import type { Session } from "../auth/session";
import "../i18n";

/** Options for `renderWithProviders`. */
export interface RenderOptions {
  /** Initial router entries (defaults to `['/']`). */
  routerEntries?: string[];
  /** A session to seed into `sessionStorage` before mounting (simulates a signed-in user). */
  session?: Session;
  /** A shared QueryClient to observe cache state across the test. */
  queryClient?: QueryClient;
}

/**
 * Build a fresh QueryClient configured like production (no retry).
 *
 * Returns:
 *   A new QueryClient.
 */
export function newTestQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/**
 * Render a component inside the app's providers.
 *
 * Args:
 *   ui: The element under test.
 *   options: Optional router entries, a seeded session, and a shared QueryClient.
 *
 * Returns:
 *   The Testing Library render result.
 */
export function renderWithProviders(ui: ReactElement, options: RenderOptions = {}): RenderResult {
  if (options.session) {
    sessionStorage.setItem("mfo.auth.session", JSON.stringify(options.session));
  }
  const queryClient = options.queryClient ?? newTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }): ReactElement {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={options.routerEntries ?? ["/"]}>{children}</MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper });
}

/** A minimal stand-in for a `fetch` response. */
export interface FakeResponse {
  status?: number;
  /** The JSON body returned by `response.json()`. */
  json?: unknown;
  /**
   * Content-Type header; defaults to `application/json` for 2xx and `application/problem+json` for
   * errors. Pass `null` to omit it, or an explicit value for near-match negative tests.
   */
  contentType?: string | null;
  /** Value for the `X-Correlation-ID` response header. */
  correlationId?: string;
  /** Value for the `Retry-After` response header. */
  retryAfter?: string;
  /** When true, `response.json()` rejects (simulates a truncated/invalid body). */
  invalidJson?: boolean;
}

/**
 * Build a `Response`-like object for the fetch stub.
 *
 * Args:
 *   fake: The desired status, body, and headers.
 *
 * Returns:
 *   An object exposing the subset of the `Response` API the client uses.
 */
export function makeResponse(fake: FakeResponse): Response {
  const status = fake.status ?? 200;
  const headers = new Headers();
  // Default to the media type the real gateway uses: application/json for success and
  // application/problem+json for errors (RFC 7807). Tests override it explicitly for near-match
  // negative cases.
  const defaultContentType = status >= 400 ? "application/problem+json" : "application/json";
  const contentType = fake.contentType === undefined ? defaultContentType : fake.contentType;
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  if (fake.correlationId) {
    headers.set("X-Correlation-ID", fake.correlationId);
  }
  if (fake.retryAfter) {
    headers.set("Retry-After", fake.retryAfter);
  }
  return {
    ok: status >= 200 && status < 300,
    status,
    headers,
    json: async () => {
      if (fake.invalidJson) {
        throw new SyntaxError("invalid JSON");
      }
      return fake.json;
    },
  } as Response;
}

/**
 * Install a `fetch` stub that returns the given responses in order.
 *
 * Args:
 *   responses: The canned responses, one per expected call (the last repeats).
 *
 * Returns:
 *   The Vitest mock function so tests can assert on call arguments.
 */
export function stubFetch(responses: FakeResponse[]): ReturnType<typeof vi.fn> {
  const queue = [...responses];
  const fn = vi.fn(async () => {
    const next = queue.shift() ?? responses[responses.length - 1];
    return makeResponse(next as FakeResponse);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** A pending fetch call that a test can resolve or reject on demand. */
export interface DeferredCall {
  /** The URL the client requested. */
  url: string;
  /** The request init (method, headers, signal). */
  init: RequestInit;
  /** Resolve this call with a fake response. */
  resolve: (response: FakeResponse) => void;
  /** Reject this call (for example, to simulate an abort). */
  reject: (error: unknown) => void;
  /** The abort signal passed to `fetch`, if any. */
  signal: AbortSignal | null;
}

/**
 * Install a `fetch` stub whose calls stay pending until the test resolves them.
 *
 * Each invocation pushes a `DeferredCall` onto the returned array and, when the caller's
 * `AbortSignal` fires, rejects the call with an `AbortError` (mirroring the browser), so
 * cancellation and stale-response tests are deterministic.
 *
 * Returns:
 *   The list of pending calls, appended to as `fetch` is invoked.
 */
export function stubDeferredFetch(): DeferredCall[] {
  const calls: DeferredCall[] = [];
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    return new Promise<Response>((resolvePromise, rejectPromise) => {
      const signal = init?.signal ?? null;
      const call: DeferredCall = {
        url: String(input),
        init: init ?? {},
        signal,
        resolve: (response) => resolvePromise(makeResponse(response)),
        reject: (error) => rejectPromise(error),
      };
      if (signal) {
        signal.addEventListener(
          "abort",
          () => rejectPromise(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      }
      calls.push(call);
    });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

/** A seeded employee session usable by tests that need an authenticated caller. */
export const TEST_SESSION: Session = {
  accessToken: "test-token",
  subject: "00000000-0000-0000-0000-000000000001",
  username: "employee",
  roles: ["EMPLOYEE"],
  permissions: ["ticket:read"],
};

/** A second distinct session, for cross-user cache-isolation tests. */
export const TEST_SESSION_B: Session = {
  accessToken: "test-token-b",
  subject: "00000000-0000-0000-0000-0000000000b2",
  username: "supervisor",
  roles: ["SUPERVISOR"],
  permissions: ["ticket:read"],
};
