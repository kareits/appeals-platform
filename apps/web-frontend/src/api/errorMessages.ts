/**
 * Mapping from an API/transport error to a localized message key.
 *
 * Keeps user-facing copy separated from diagnostics: the returned key selects a safe localized
 * message; the correlation id (for support) is read separately from the error and never embedded in
 * the message. Each contracted gateway status has a distinct message so operators can tell input,
 * permission, throttling, timeout, and service failures apart.
 */
import { ApiError, NetworkError, ProtocolError, TimeoutError } from "./errors";

/**
 * Select a localized message key for an error.
 *
 * Args:
 *   error: The error thrown by an API call.
 *
 * Returns:
 *   The i18n key under the `errors.*` namespace describing the failure.
 */
export function errorMessageKey(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 400:
        return "errors.badRequest";
      case 401:
        return "errors.unauthorized";
      case 403:
        return "errors.forbidden";
      case 404:
        return "errors.notFound";
      case 409:
        return "errors.conflict";
      case 413:
        return "errors.tooLarge";
      case 422:
        return "errors.validation";
      case 429:
        return "errors.rateLimited";
      case 502:
        return "errors.badGateway";
      case 503:
        return "errors.unavailable";
      case 504:
        return "errors.gatewayTimeout";
      default:
        return error.status >= 500 ? "errors.server" : "errors.generic";
    }
  }
  if (error instanceof TimeoutError) {
    return "errors.timeout";
  }
  if (error instanceof NetworkError) {
    return "errors.network";
  }
  if (error instanceof ProtocolError) {
    return "errors.protocol";
  }
  return "errors.generic";
}

/**
 * Extract the diagnostic correlation id from an error, when present.
 *
 * Args:
 *   error: The error thrown by an API call.
 *
 * Returns:
 *   The correlation id for support/diagnostics, or null.
 */
export function errorCorrelationId(error: unknown): string | null {
  if (error instanceof ApiError || error instanceof ProtocolError) {
    return error.correlationId;
  }
  return null;
}

/**
 * The bounded Retry-After hint (seconds) for a 429, when the gateway supplied one.
 *
 * Args:
 *   error: The error thrown by an API call.
 *
 * Returns:
 *   The seconds to wait, or null when not applicable.
 */
export function retryAfterSeconds(error: unknown): number | null {
  if (error instanceof ApiError && error.status === 429) {
    return error.retryAfterSeconds;
  }
  return null;
}
