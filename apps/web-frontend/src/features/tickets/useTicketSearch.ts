/**
 * Data hook for appeal search.
 *
 * Wraps the gateway search endpoint in a TanStack Query so the list page gets caching, loading and
 * error states, and automatic refetch when the applied filters change. The query key is scoped by
 * the authenticated subject so one user's cached results can never be read under another user's
 * session (CR-WEB-HIGH-001). The query's `AbortSignal` is threaded to `fetch`, so a superseded
 * search, a navigation, an unmount, or a logout cancels the in-flight request (CR-WEB-MEDIUM-002).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useAuth } from "../../auth/context";
import { searchTickets } from "../../api/tickets";
import type { PaginatedTickets, TicketSearchFilters } from "../../api/types";

/**
 * Query appeals for the given filters, scoped to the current subject.
 *
 * Args:
 *   filters: The applied search filters and pagination controls.
 *
 * Returns:
 *   The TanStack Query result for the paginated appeals.
 */
export function useTicketSearch(
  filters: TicketSearchFilters,
): UseQueryResult<PaginatedTickets, unknown> {
  const { client, session } = useAuth();
  const subject = session?.subject ?? "anonymous";
  return useQuery({
    // Subject is part of the key so results are never shared across sessions.
    queryKey: ["tickets", subject, filters],
    queryFn: ({ signal }) => searchTickets(client, filters, signal),
    enabled: session !== null,
    // Keeps the previous page visible while the next loads; the observer is per-mount and the
    // subject is fixed for that mount, so this never carries data across users.
    placeholderData: (previous) => previous,
  });
}
