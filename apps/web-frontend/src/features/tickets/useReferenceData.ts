/**
 * Data hook for reference-dictionary lookups.
 *
 * Wraps the gateway reference-data endpoint in a TanStack Query so the registration form gets
 * caching, loading, and error states for its select controls. The query key is scoped by the
 * authenticated subject (consistent with the appeal search, CR-WEB-HIGH-001) and the requested
 * types. Reference data changes rarely, so it is cached with a long stale time.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useAuth } from "../../auth/context";
import { getReferenceData } from "../../api/reference";
import type { ReferenceDataResponse } from "../../api/types";

/** Dictionaries the registration form needs (intake channel, classification codes, gender). */
export const REGISTRATION_DICTIONARIES = [
  "channel",
  "product",
  "classifier",
  "priority",
  "gender",
] as const;

/** How long reference data is considered fresh; it is business-configured and changes rarely. */
const REFERENCE_STALE_MS = 5 * 60 * 1000;

/**
 * Query the reference dictionaries used by the registration form, scoped to the current subject.
 *
 * Args:
 *   types: The dictionary types to fetch (defaults to the registration form's dictionaries).
 *
 * Returns:
 *   The TanStack Query result for the reference-data response.
 */
export function useReferenceData(
  types: readonly string[] = REGISTRATION_DICTIONARIES,
): UseQueryResult<ReferenceDataResponse, unknown> {
  const { client, session } = useAuth();
  const subject = session?.subject ?? "anonymous";
  return useQuery({
    queryKey: ["reference-data", subject, [...types]],
    queryFn: ({ signal }) => getReferenceData(client, types, signal),
    enabled: session !== null,
    staleTime: REFERENCE_STALE_MS,
  });
}
