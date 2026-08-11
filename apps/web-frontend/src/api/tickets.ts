/**
 * Appeal (ticket) endpoint wrappers over the BFF gateway.
 *
 * TASK_01E-2 uses the read-only search endpoint; 01E-3 adds registration; 01E-4 adds the appeal-card
 * workspace read and the card commands (update, classify, decision, close, legal hold, comments).
 * Responses are validated at runtime (never trusted via `as T`).
 */
import type { ApiClient } from "./client";
import {
  decodeComment,
  decodePaginatedTickets,
  decodeTicketResponse,
  decodeWorkspace,
} from "./decoders";
import type {
  ClassifyRequest,
  CloseTicketRequest,
  CommentRequest,
  CommentResponse,
  CreateTicketRequest,
  LegalHoldRequest,
  PaginatedTickets,
  RecordDecisionRequest,
  TicketResponse,
  TicketSearchFilters,
  UpdateTicketRequest,
  Workspace,
} from "./types";

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

/**
 * Register an appeal manually.
 *
 * Requires the `ticket:create` permission (enforced by the gateway and the Ticket Service). The
 * `Idempotency-Key` header makes a retried submission safe: the same caller replaying the same key
 * receives the originally registered appeal instead of a duplicate. The response is validated at
 * runtime.
 *
 * Args:
 *   client: The gateway client.
 *   body: The registration request.
 *   idempotencyKey: A per-submission key making the create retry-safe.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The registered (or idempotently replayed) appeal card.
 *
 * Raises:
 *   ApiError: 401 unauthenticated, 403 without `ticket:create`, 409 on an idempotency conflict, 422
 *     for invalid input.
 *   ProtocolError: When the response body fails validation.
 */
export function createTicket(
  client: ApiClient,
  body: CreateTicketRequest,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<TicketResponse> {
  return client.request<TicketResponse>("/tickets", {
    method: "POST",
    body,
    headers: { "Idempotency-Key": idempotencyKey },
    signal,
    decode: decodeTicketResponse,
  });
}

/**
 * Read the aggregated appeal workspace (card + comments + later-phase placeholders).
 *
 * Requires the `ticket:read` permission. The gateway classifies downstream failures (a missing
 * appeal is 404, an auth failure propagates as 401/403); only the optional comments section degrades
 * while the rest still returns. The response is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The validated workspace envelope (possibly degraded).
 *
 * Raises:
 *   ApiError: 401 unauthenticated, 403 without `ticket:read`, 404 for an unknown appeal.
 *   ProtocolError: When the response body fails validation.
 */
export function getWorkspace(
  client: ApiClient,
  ticketId: string,
  signal?: AbortSignal,
): Promise<Workspace> {
  return client.request<Workspace>(`/tickets/${ticketId}/workspace`, {
    method: "GET",
    signal,
    decode: decodeWorkspace,
  });
}

/**
 * Update editable appeal-card details (subject/description/channel/contract number).
 *
 * Requires the `ticket:update` permission. Status, stage, assignee, and team are never editable
 * here (ADR-0008). `expectedVersion` enforces optimistic locking; a stale version yields 409. The
 * response is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   body: The partial update with the expected version.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The updated appeal card.
 *
 * Raises:
 *   ApiError: 401/403 for auth failures, 404 for an unknown appeal, 409 on a version conflict, 422
 *     for invalid input.
 *   ProtocolError: When the response body fails validation.
 */
export function updateTicket(
  client: ApiClient,
  ticketId: string,
  body: UpdateTicketRequest,
  signal?: AbortSignal,
): Promise<TicketResponse> {
  return client.request<TicketResponse>(`/tickets/${ticketId}`, {
    method: "PATCH",
    body,
    signal,
    decode: decodeTicketResponse,
  });
}

/**
 * Re-classify an appeal (product/classifier/priority).
 *
 * Requires the `ticket:classify` permission. `expectedVersion` enforces optimistic locking. The
 * response is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   body: The classification with the expected version.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The reclassified appeal card.
 *
 * Raises:
 *   ApiError: 401/403 for auth failures, 404 for an unknown appeal, 409 on a version conflict, 422
 *     for invalid input.
 *   ProtocolError: When the response body fails validation.
 */
export function classifyTicket(
  client: ApiClient,
  ticketId: string,
  body: ClassifyRequest,
  signal?: AbortSignal,
): Promise<TicketResponse> {
  return client.request<TicketResponse>(`/tickets/${ticketId}/classify`, {
    method: "POST",
    body,
    signal,
    decode: decodeTicketResponse,
  });
}

/**
 * Record the regulatory decision on an appeal.
 *
 * Requires the `ticket:decide` permission. The deciding employee is derived server-side from the
 * authenticated caller (trusted actor). `expectedVersion` enforces optimistic locking. The response
 * is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   body: The decision with the expected version.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The appeal card with the recorded decision.
 *
 * Raises:
 *   ApiError: 401/403 for auth failures, 404 for an unknown appeal, 409 on a version conflict, 422
 *     for invalid input.
 *   ProtocolError: When the response body fails validation.
 */
export function recordDecision(
  client: ApiClient,
  ticketId: string,
  body: RecordDecisionRequest,
  signal?: AbortSignal,
): Promise<TicketResponse> {
  return client.request<TicketResponse>(`/tickets/${ticketId}/decision`, {
    method: "POST",
    body,
    signal,
    decode: decodeTicketResponse,
  });
}

/**
 * Close an appeal.
 *
 * Requires the `ticket:close` permission. The Ticket Service enforces the regulatory prerequisites
 * (a prior decision, a closure reason, and a response date or a recorded reason for its absence);
 * an unmet prerequisite is surfaced as a 4xx. `expectedVersion` enforces optimistic locking. The
 * response is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   body: The closure request with the expected version.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The closed appeal card.
 *
 * Raises:
 *   ApiError: 401/403 for auth failures, 404 for an unknown appeal, 409 on a version conflict, 422
 *     when a close prerequisite is unmet.
 *   ProtocolError: When the response body fails validation.
 */
export function closeTicket(
  client: ApiClient,
  ticketId: string,
  body: CloseTicketRequest,
  signal?: AbortSignal,
): Promise<TicketResponse> {
  return client.request<TicketResponse>(`/tickets/${ticketId}/close`, {
    method: "POST",
    body,
    signal,
    decode: decodeTicketResponse,
  });
}

/**
 * Set or clear the legal hold on an appeal.
 *
 * Requires the `ticket:legal_hold` permission. `expectedVersion` enforces optimistic locking. The
 * response is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   body: The legal-hold request with the expected version.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The appeal card with the updated legal-hold flag.
 *
 * Raises:
 *   ApiError: 401/403 for auth failures, 404 for an unknown appeal, 409 on a version conflict.
 *   ProtocolError: When the response body fails validation.
 */
export function setLegalHold(
  client: ApiClient,
  ticketId: string,
  body: LegalHoldRequest,
  signal?: AbortSignal,
): Promise<TicketResponse> {
  return client.request<TicketResponse>(`/tickets/${ticketId}/legal-hold`, {
    method: "POST",
    body,
    signal,
    decode: decodeTicketResponse,
  });
}

/**
 * Add a comment to an appeal.
 *
 * Requires the `ticket:comment` permission. The author is derived server-side from the
 * authenticated caller (trusted actor). The response is validated at runtime.
 *
 * Args:
 *   client: The gateway client.
 *   ticketId: The appeal identifier.
 *   body: The comment text.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The created comment.
 *
 * Raises:
 *   ApiError: 401/403 for auth failures, 404 for an unknown appeal, 422 for invalid input.
 *   ProtocolError: When the response body fails validation.
 */
export function addComment(
  client: ApiClient,
  ticketId: string,
  body: CommentRequest,
  signal?: AbortSignal,
): Promise<CommentResponse> {
  return client.request<CommentResponse>(`/tickets/${ticketId}/comments`, {
    method: "POST",
    body,
    signal,
    decode: decodeComment,
  });
}
