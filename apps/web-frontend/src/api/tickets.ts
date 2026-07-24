/**
 * Appeal (ticket) endpoint wrappers over the BFF gateway.
 *
 * TASK_01E-2 uses the read-only search endpoint. Registration and card commands are added in later
 * frontend subtasks (01E-3/01E-4). Responses are validated at runtime (never trusted via `as T`).
 */
import type { ApiClient } from "./client";
import { decodePaginatedTickets } from "./decoders";
import type { PaginatedTickets, TicketSearchFilters } from "./types";

/**
 * Search appeals with optional filters and pagination.
 *
 * Requires the `ticket:read` permission (enforced by the gateway and the Ticket Service). Empty
 * filter values are omitted from the query. The abort signal (from TanStack Query) is threaded to
 * `fetch` so a superseded or abandoned search is cancelled.
 *
 * Args:
 *   client: The gateway client.
 *   filters: Search filters and pagination controls.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   A validated page of matching appeal summaries.
 *
 * Raises:
 *   ApiError: 401 unauthenticated, 403 without `ticket:read`, 400 for an invalid query.
 *   ProtocolError: When the response body fails validation.
 */
export function searchTickets(
  client: ApiClient,
  filters: TicketSearchFilters,
  signal?: AbortSignal,
): Promise<PaginatedTickets> {
  return client.request<PaginatedTickets>("/tickets", {
    method: "GET",
    query: { ...filters },
    signal,
    decode: decodePaginatedTickets,
  });
}
