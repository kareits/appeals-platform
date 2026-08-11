/**
 * Data hook for the appeal-card workspace.
 *
 * Wraps the gateway workspace endpoint in a TanStack Query so the appeal card gets caching, loading,
 * and error states. The query key is scoped by the authenticated subject (consistent with the appeal
 * search and reference data, CR-WEB-HIGH-001) and the appeal id, so one user's cached card is never
 * served to another after a re-login in the same tab.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useAuth } from "../../auth/context";
import { getWorkspace } from "../../api/tickets";
import type { Workspace } from "../../api/types";

/**
 * Build the subject-scoped query key for an appeal workspace.
 *
 * Args:
 *   subject: The authenticated subject identifier (or a stand-in when signed out).
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The query key array.
 */
export function workspaceQueryKey(subject: string, ticketId: string): readonly unknown[] {
  return ["workspace", subject, ticketId];
}

/**
 * Query the aggregated workspace for one appeal, scoped to the current subject.
 *
 * Args:
 *   ticketId: The appeal identifier to load.
 *
 * Returns:
 *   The TanStack Query result for the workspace envelope.
 */
export function useWorkspace(ticketId: string): UseQueryResult<Workspace, unknown> {
  const { client, session } = useAuth();
  const subject = session?.subject ?? "anonymous";
  return useQuery({
    queryKey: workspaceQueryKey(subject, ticketId),
    queryFn: ({ signal }) => getWorkspace(client, ticketId, signal),
    enabled: session !== null,
  });
}
