/**
 * Minimal same-origin HTTP client for the BFF gateway.
 *
 * All calls target the gateway's `/api/v1` surface on the same origin (Vite proxies `/api` in dev;
 * the reverse proxy routes it in production). The client attaches the bearer token when present,
 * generates an `X-Correlation-ID` for tracing, threads an `AbortSignal` through to `fetch` so
 * superseded/abandoned requests are cancelled, and enforces the wire contract on responses: 2xx
 * bodies are read only under an `application/json` media type and validated by a caller-supplied
 * decoder (never trusted via `as T`). Non-2xx responses become `ApiError` (with the validated
 * problem, correlation id, and bounded Retry-After); contract violations become `ProtocolError`;
 * transport failures become `NetworkError`/`TimeoutError`; a caller-initiated abort is re-raised so
 * the query layer treats it as a silent cancellation. A `401` invokes the unauthorized handler.
 */
import { ApiError, NetworkError, ProtocolError, TimeoutError } from "./errors";
import { decodeProblem } from "./decoders";

/** Base path of the gateway API (same origin as the SPA). */
const API_BASE = "/api/v1";

/** Client-side request deadline; a slow gateway fails as a timeout rather than hanging. */
const REQUEST_TIMEOUT_MS = 15_000;

/** Upper bound (seconds) accepted for a Retry-After hint, to avoid an unbounded wait suggestion. */
const MAX_RETRY_AFTER_SECONDS = 3600;

/** Dependencies the client resolves lazily on each request. */
export interface ApiClientDeps {
  /** Returns the current bearer token, or null when the user is not authenticated. */
  getToken: () => string | null;
  /** Invoked when the gateway returns 401 so the app can clear its session. */
  onUnauthorized: () => void;
}

/** Options for a single request. */
interface RequestOptions<T> {
  method?: string;
  /** JSON-serializable request body. */
  body?: unknown;
  /** Query parameters; null/undefined/empty values are omitted. */
  query?: Record<string, string | number | undefined | null>;
  /** Additional headers (for example, Idempotency-Key). */
  headers?: Record<string, string>;
  /** Cancellation signal from the caller (for example, TanStack Query). */
  signal?: AbortSignal;
  /** Runtime validator applied to a 2xx JSON body; the response is never trusted via `as T`. */
  decode: (raw: unknown) => T;
}

/**
 * Generate a correlation identifier for a request.
 *
 * Uses the platform `crypto.randomUUID` when available and falls back to a timestamped random
 * string in environments that lack it (older test runners).
 */
function newCorrelationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `cid-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Serialize query parameters, omitting empty values.
 *
 * Args:
 *   query: The raw query map.
 *
 * Returns:
 *   A URL-encoded query string beginning with `?`, or an empty string when nothing is set.
 */
function buildQuery(query: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    params.append(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

/**
 * Whether an error is a caller-initiated abort (as opposed to a timeout or network failure).
 *
 * Args:
 *   error: The thrown value.
 *
 * Returns:
 *   True when the value represents an `AbortError` DOMException.
 */
function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Allowed characters and length for a correlation id copied into diagnostics. */
const CORRELATION_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;

/**
 * Parse the base media type from a Content-Type header (drop parameters, trim, lowercase).
 *
 * Args:
 *   contentType: The raw `Content-Type` header value (or null).
 *
 * Returns:
 *   The lowercased base media type, or null when absent.
 */
function baseMediaType(contentType: string | null): string | null {
  if (!contentType) {
    return null;
  }
  const semicolon = contentType.indexOf(";");
  const base = (semicolon === -1 ? contentType : contentType.slice(0, semicolon))
    .trim()
    .toLowerCase();
  return base === "" ? null : base;
}

/** Exact media type required of a successful JSON response. */
const JSON_MEDIA_TYPE = "application/json";

/** Exact media type required of an RFC 7807 error response. */
const PROBLEM_MEDIA_TYPE = "application/problem+json";

/**
 * Whether a media type is exactly `application/json` (success responses).
 *
 * The comparison is exact after stripping parameters such as `charset`, so near matches like
 * `application/jsonp` or `text/application/json` are rejected — the same fail-closed rule enforced
 * at the BFF boundary.
 *
 * Args:
 *   contentType: The raw `Content-Type` header value (or null).
 *
 * Returns:
 *   True only when the base media type is exactly `application/json`.
 */
function isJsonMediaType(contentType: string | null): boolean {
  return baseMediaType(contentType) === JSON_MEDIA_TYPE;
}

/**
 * Whether a media type is exactly `application/problem+json` (RFC 7807 error responses).
 *
 * Args:
 *   contentType: The raw `Content-Type` header value (or null).
 *
 * Returns:
 *   True only when the base media type is exactly `application/problem+json`.
 */
function isProblemMediaType(contentType: string | null): boolean {
  return baseMediaType(contentType) === PROBLEM_MEDIA_TYPE;
}

/**
 * Validate and bound a correlation id before it is retained for diagnostics.
 *
 * Args:
 *   raw: The raw `X-Correlation-ID` header value (or null).
 *
 * Returns:
 *   The correlation id when it matches the safe charset/length policy, otherwise null.
 */
function sanitizeCorrelationId(raw: string | null): string | null {
  if (raw && CORRELATION_ID_RE.test(raw)) {
    return raw;
  }
  return null;
}

/**
 * Parse a bounded Retry-After header value in delta-seconds.
 *
 * Args:
 *   header: The raw `Retry-After` header value (or null).
 *
 * Returns:
 *   The bounded non-negative integer seconds, or null when absent/invalid/out of range.
 */
function parseRetryAfter(header: string | null): number | null {
  if (!header) {
    return null;
  }
  const seconds = Number(header.trim());
  if (!Number.isInteger(seconds) || seconds < 0 || seconds > MAX_RETRY_AFTER_SECONDS) {
    return null;
  }
  return seconds;
}

/**
 * A typed gateway client bound to a token provider and an unauthorized handler.
 *
 * Instances are created by `createApiClient` and expose a single generic `request` method used by
 * the endpoint wrappers in `auth.ts` and `tickets.ts`.
 */
export class ApiClient {
  private readonly deps: ApiClientDeps;

  /**
   * Bind a client to its runtime dependencies.
   *
   * Args:
   *   deps: The token accessor and unauthorized handler.
   */
  constructor(deps: ApiClientDeps) {
    this.deps = deps;
  }

  /**
   * Perform a gateway request and return the validated JSON body.
   *
   * Attaches the bearer token and correlation id, threads the caller's abort signal (plus a
   * client-side timeout) into `fetch`, and enforces the wire contract on the response.
   *
   * Args:
   *   path: The path under `/api/v1` (for example, `/tickets`).
   *   options: Method, body, query, headers, abort signal, and the response decoder.
   *
   * Returns:
   *   The validated response typed as `T`.
   *
   * Raises:
   *   ApiError: For any non-2xx response.
   *   ProtocolError: For a wrong media type, invalid JSON, or a body failing validation.
   *   NetworkError: When the request fails at the transport layer.
   *   TimeoutError: When the request exceeds the client-side deadline.
   *   DOMException: The original `AbortError` when the caller cancels the request.
   */
  async request<T>(path: string, options: RequestOptions<T>): Promise<T> {
    const { method = "GET", body, query, headers = {}, signal, decode } = options;
    const token = this.deps.getToken();

    const requestHeaders: Record<string, string> = {
      Accept: "application/json",
      "X-Correlation-ID": newCorrelationId(),
      ...headers,
    };
    if (body !== undefined) {
      requestHeaders["Content-Type"] = "application/json";
    }
    if (token) {
      requestHeaders["Authorization"] = `Bearer ${token}`;
    }

    const url = `${API_BASE}${path}${query ? buildQuery(query) : ""}`;

    // Combine the caller's cancellation with a client-side timeout on a local controller, so the
    // three outcomes (caller abort / timeout / network) stay distinguishable to the UI.
    const controller = new AbortController();
    let timedOut = false;
    const onCallerAbort = (): void => controller.abort(signal?.reason);
    if (signal) {
      if (signal.aborted) {
        controller.abort(signal.reason);
      } else {
        signal.addEventListener("abort", onCallerAbort, { once: true });
      }
    }
    const timeoutId = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers: requestHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      // Caller-initiated cancellation is surfaced as-is so the query layer treats it as silent.
      if (signal?.aborted) {
        throw error;
      }
      if (timedOut) {
        throw new TimeoutError();
      }
      if (isAbortError(error)) {
        throw error;
      }
      throw new NetworkError();
    } finally {
      clearTimeout(timeoutId);
      if (signal) {
        signal.removeEventListener("abort", onCallerAbort);
      }
    }

    const correlationId = sanitizeCorrelationId(response.headers.get("X-Correlation-ID"));

    if (response.status === 401) {
      this.deps.onUnauthorized();
    }

    if (!response.ok) {
      const contentType = response.headers.get("Content-Type");
      // An RFC 7807 error is accepted only under an exact application/problem+json media type. Any
      // other declared error media type (application/json, application/jsonp,
      // application/problem+jsonp, ...) is a protocol violation and fails closed; a bodyless error
      // (no Content-Type) still surfaces its status.
      if (baseMediaType(contentType) !== null && !isProblemMediaType(contentType)) {
        throw new ProtocolError("unexpected error media type", {
          status: response.status,
          correlationId,
        });
      }
      throw new ApiError(response.status, {
        problem: isProblemMediaType(contentType) ? await this.readProblem(response) : null,
        correlationId,
        retryAfterSeconds: parseRetryAfter(response.headers.get("Retry-After")),
      });
    }

    if (!isJsonMediaType(response.headers.get("Content-Type"))) {
      throw new ProtocolError("unexpected response media type", {
        status: response.status,
        correlationId,
      });
    }

    let raw: unknown;
    try {
      raw = await response.json();
    } catch {
      throw new ProtocolError("invalid JSON response", {
        status: response.status,
        correlationId,
      });
    }

    try {
      return decode(raw);
    } catch (error) {
      if (error instanceof ProtocolError) {
        throw new ProtocolError(error.message, { status: response.status, correlationId });
      }
      throw new ProtocolError("response failed validation", {
        status: response.status,
        correlationId,
      });
    }
  }

  /**
   * Read and validate an RFC 7807 problem body from a failed response.
   *
   * The caller has already confirmed the media type is exactly `application/problem+json`, so this
   * only parses and validates the body, yielding null when the JSON is invalid or fails validation
   * (the status is still surfaced by the enclosing `ApiError`).
   *
   * Args:
   *   response: The failed HTTP response.
   *
   * Returns:
   *   The validated problem, or null when unavailable.
   */
  private async readProblem(response: Response): Promise<ReturnType<typeof decodeProblem>> {
    try {
      return decodeProblem(await response.json());
    } catch {
      return null;
    }
  }
}

/**
 * Create a gateway API client.
 *
 * Args:
 *   deps: The token accessor and unauthorized handler.
 *
 * Returns:
 *   A configured `ApiClient`.
 */
export function createApiClient(deps: ApiClientDeps): ApiClient {
  return new ApiClient(deps);
}
