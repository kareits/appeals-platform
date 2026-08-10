/**
 * Mutation hook for manual appeal registration.
 *
 * Wraps the gateway create endpoint in a TanStack mutation. On success it invalidates the current
 * subject's appeal-search queries so a freshly registered appeal appears in the list. The caller
 * supplies a stable per-submission idempotency key so a retried submission (after a transient
 * failure) reconciles to the original appeal instead of creating a duplicate.
 */
import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useAuth } from "../../auth/context";
import { createTicket } from "../../api/tickets";
import type { CreateTicketRequest, TicketResponse } from "../../api/types";

/** Variables for a registration submission: the request body and its idempotency key. */
export interface CreateTicketVariables {
  body: CreateTicketRequest;
  idempotencyKey: string;
}

/**
 * Provide a mutation that registers an appeal and refreshes the appeal list on success.
 *
 * Returns:
 *   The TanStack mutation result for the registration.
 */
export function useCreateTicket(): UseMutationResult<
  TicketResponse,
  unknown,
  CreateTicketVariables
> {
  const { client, session } = useAuth();
  const queryClient = useQueryClient();
  const subject = session?.subject ?? "anonymous";
  return useMutation({
    mutationFn: ({ body, idempotencyKey }: CreateTicketVariables) =>
      createTicket(client, body, idempotencyKey),
    onSuccess: () => {
      // Refresh only this subject's cached searches so the new appeal shows up on the list.
      void queryClient.invalidateQueries({ queryKey: ["tickets", subject] });
    },
  });
}
