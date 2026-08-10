/**
 * Reference-dictionary endpoint wrapper over the BFF gateway.
 *
 * Reference data (channel, product, classifier, priority, gender, and so on) populates the
 * registration form's select controls. Responses are validated at runtime (never trusted via
 * `as T`).
 */
import type { ApiClient } from "./client";
import { decodeReferenceData } from "./decoders";
import type { ReferenceDataResponse } from "./types";

/**
 * Fetch active reference-dictionary entries, optionally restricted to specific dictionary types.
 *
 * Requires the `ticket:read` permission (enforced by the gateway and the Ticket Service). When
 * `types` is provided, only those dictionaries are returned; otherwise every active entry is
 * returned. The abort signal (from TanStack Query) is threaded to `fetch` so an abandoned request
 * is cancelled.
 *
 * Args:
 *   client: The gateway client.
 *   types: Optional dictionary types to include (for example, `["product", "priority"]`).
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   A validated set of active reference entries.
 *
 * Raises:
 *   ApiError: 401 unauthenticated, 403 without `ticket:read`.
 *   ProtocolError: When the response body fails validation.
 */
export function getReferenceData(
  client: ApiClient,
  types?: readonly string[],
  signal?: AbortSignal,
): Promise<ReferenceDataResponse> {
  const query = types && types.length > 0 ? { types: types.join(",") } : undefined;
  return client.request<ReferenceDataResponse>("/reference-data", {
    method: "GET",
    query,
    signal,
    decode: decodeReferenceData,
  });
}
