/**
 * Error types raised by the API boundary.
 *
 * `ApiError` represents a non-2xx gateway response (with the validated RFC 7807 problem, the
 * diagnostic correlation id, and a bounded Retry-After when present). `ProtocolError` represents a
 * response that violated the wire contract — wrong media type, invalid JSON, or a body that failed
 * runtime validation — so the caller can fail closed instead of trusting malformed data or crashing
 * during render. Both keep the correlation id for diagnostics but never for display.
 */
import type { ProblemDetails } from "./types";

/**
 * Error raised for any non-2xx gateway response.
 *
 * Carries the HTTP status, the validated RFC 7807 problem (when the body was a valid problem
 * document), the diagnostic correlation id, and the bounded Retry-After (seconds) when the response
 * supplied one (for example, on 429).
 */
export class ApiError extends Error {
  /** The HTTP status code of the failed response. */
  readonly status: number;
  /** The validated RFC 7807 problem body, when the response carried a valid one. */
  readonly problem: ProblemDetails | null;
  /** The correlation id from the response, for diagnostics only (never shown to the user). */
  readonly correlationId: string | null;
  /** The bounded Retry-After value in seconds, when the response supplied a valid one. */
  readonly retryAfterSeconds: number | null;

  /**
   * Build an API error.
   *
   * Args:
   *   status: The HTTP status code.
   *   options: The validated problem, correlation id, and bounded Retry-After.
   */
  constructor(
    status: number,
    options: {
      problem?: ProblemDetails | null;
      correlationId?: string | null;
      retryAfterSeconds?: number | null;
    } = {},
  ) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.problem = options.problem ?? null;
    this.correlationId = options.correlationId ?? null;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
  }
}

/**
 * Error raised when the request failed at the transport layer (not an HTTP status).
 *
 * Represents a `fetch` rejection that is not a caller-initiated cancellation — for example, the
 * gateway is unreachable or the connection dropped. Distinct from `ApiError` and `TimeoutError` so
 * the UI can show a dedicated network state.
 */
export class NetworkError extends Error {
  /**
   * Build a network error.
   *
   * Args:
   *   message: A short, non-sensitive description.
   */
  constructor(message = "network request failed") {
    super(message);
    this.name = "NetworkError";
  }
}

/**
 * Error raised when a request exceeded the client-side deadline.
 *
 * Distinct from a caller-initiated cancellation (which is surfaced silently) and from a network
 * failure, so the UI can show a dedicated timeout state.
 */
export class TimeoutError extends Error {
  /**
   * Build a timeout error.
   *
   * Args:
   *   message: A short, non-sensitive description.
   */
  constructor(message = "request timed out") {
    super(message);
    this.name = "TimeoutError";
  }
}

/**
 * Error raised when a response violates the wire contract.
 *
 * Used for a wrong/absent media type, invalid JSON, or a body that failed runtime validation. It is
 * deliberately distinct from `ApiError` so the UI can present a single safe "unexpected response"
 * state instead of rendering unvalidated data.
 */
export class ProtocolError extends Error {
  /** The HTTP status the malformed response carried, when known. */
  readonly status: number | null;
  /** The correlation id from the response, for diagnostics only. */
  readonly correlationId: string | null;

  /**
   * Build a protocol error.
   *
   * Args:
   *   message: A short, non-sensitive description of the violation.
   *   options: The originating status and correlation id, when known.
   */
  constructor(
    message: string,
    options: { status?: number | null; correlationId?: string | null } = {},
  ) {
    super(message);
    this.name = "ProtocolError";
    this.status = options.status ?? null;
    this.correlationId = options.correlationId ?? null;
  }
}
