/**
 * Mutation hooks for the appeal-card commands.
 *
 * Each hook wraps one gateway card command (update, classify, decision, close, legal hold, comment)
 * in a TanStack mutation and, on success, invalidates the subject-scoped workspace query so the card
 * and comments re-read reflects the change (including the new optimistic-locking version). The hooks
 * do not enforce permissions themselves — the page gates the controls and the gateway/Ticket Service
 * enforce the claims (ADR-0008); these hooks only carry the request.
 */
import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useAuth } from "../../auth/context";
import type { ApiClient } from "../../api/client";
import {
  addComment,
  classifyTicket,
  closeTicket,
  recordDecision,
  setLegalHold,
  updateTicket,
} from "../../api/tickets";
import type {
  ClassifyRequest,
  CloseTicketRequest,
  CommentRequest,
  CommentResponse,
  LegalHoldRequest,
  RecordDecisionRequest,
  TicketResponse,
  UpdateTicketRequest,
} from "../../api/types";
import { workspaceQueryKey } from "./useWorkspace";

/**
 * Shared custom hook for a card command that refreshes the workspace on success.
 *
 * Runs the given endpoint wrapper as a TanStack mutation and, when it succeeds, invalidates the
 * subject-scoped workspace query so the card view re-reads the authoritative state and new version.
 *
 * Args:
 *   ticketId: The appeal identifier the command targets.
 *   command: The endpoint wrapper invoked with the client, appeal id, and request body.
 *
 * Returns:
 *   The TanStack mutation result for the command.
 */
function useCardMutation<TBody, TResult>(
  ticketId: string,
  command: (client: ApiClient, ticketId: string, body: TBody) => Promise<TResult>,
): UseMutationResult<TResult, unknown, TBody> {
  const { client, session } = useAuth();
  const queryClient = useQueryClient();
  const subject = session?.subject ?? "anonymous";
  return useMutation({
    mutationFn: (body: TBody) => command(client, ticketId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: workspaceQueryKey(subject, ticketId) });
    },
  });
}

/**
 * Mutation hook: update editable card details for the given appeal.
 *
 * Args:
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The update mutation.
 */
export function useUpdateTicket(
  ticketId: string,
): UseMutationResult<TicketResponse, unknown, UpdateTicketRequest> {
  return useCardMutation(ticketId, updateTicket);
}

/**
 * Mutation hook: re-classify the given appeal.
 *
 * Args:
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The classify mutation.
 */
export function useClassifyTicket(
  ticketId: string,
): UseMutationResult<TicketResponse, unknown, ClassifyRequest> {
  return useCardMutation(ticketId, classifyTicket);
}

/**
 * Mutation hook: record the decision on the given appeal.
 *
 * Args:
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The decision mutation.
 */
export function useRecordDecision(
  ticketId: string,
): UseMutationResult<TicketResponse, unknown, RecordDecisionRequest> {
  return useCardMutation(ticketId, recordDecision);
}

/**
 * Mutation hook: close the given appeal.
 *
 * Args:
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The close mutation.
 */
export function useCloseTicket(
  ticketId: string,
): UseMutationResult<TicketResponse, unknown, CloseTicketRequest> {
  return useCardMutation(ticketId, closeTicket);
}

/**
 * Mutation hook: set or clear the legal hold on the given appeal.
 *
 * Args:
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The legal-hold mutation.
 */
export function useSetLegalHold(
  ticketId: string,
): UseMutationResult<TicketResponse, unknown, LegalHoldRequest> {
  return useCardMutation(ticketId, setLegalHold);
}

/**
 * Mutation hook: add a comment to the given appeal.
 *
 * Args:
 *   ticketId: The appeal identifier.
 *
 * Returns:
 *   The add-comment mutation.
 */
export function useAddComment(
  ticketId: string,
): UseMutationResult<CommentResponse, unknown, CommentRequest> {
  return useCardMutation(ticketId, addComment);
}
