/**
 * Transport types projected from the BFF contract (`contracts/openapi/bff-service.v1.yaml`).
 *
 * These interfaces mirror the wire shapes the gateway serves for the operations this frontend uses
 * (authentication and appeal search). They are a hand-maintained projection, not a shared domain
 * model; when the BFF contract changes, update these types to match. Fields use the gateway's
 * camelCase JSON naming and ISO-8601 UTC timestamps.
 */

/** Platform roles assignable to a user (BFF `Role`). */
export type Role =
  "EMPLOYEE" | "SUPERVISOR" | "FIRST_LINE_READONLY" | "OMBUDSMAN" | "ANALYST" | "ADMIN" | "AUDITOR";

/** Credentials posted to `POST /api/v1/auth/login` (BFF `LoginRequest`). */
export interface LoginRequest {
  username: string;
  password: string;
}

/** Signed access token and resolved claims (BFF `TokenResponse`). */
export interface TokenResponse {
  accessToken: string;
  tokenType: "Bearer";
  expiresIn: number;
  subject: string;
  username: string;
  roles: Role[];
  permissions: string[];
  teams: string[];
}

/** The caller's resolved auth context (BFF `AuthContext`). */
export interface AuthContext {
  subject: string;
  username: string;
  roles: string[];
  permissions: string[];
}

/** A compact appeal representation for search results (BFF `TicketSummary`). */
export interface TicketSummary {
  id: string;
  registrationNumber: string;
  subject: string;
  currentStatusCode: string;
  currentStageCode: string;
  productCode: string;
  classifierCode: string;
  priorityCode: string;
  contractNumber: string | null;
  currentAssigneeId: string | null;
  currentTeamId: string | null;
  receivedAt: string;
  registeredAt: string;
}

/** Pagination metadata (BFF `PageMeta`). */
export interface PageMeta {
  page: number;
  pageSize: number;
  total: number;
}

/** A page of matching appeals (BFF `PaginatedTickets`). */
export interface PaginatedTickets {
  items: TicketSummary[];
  page: PageMeta;
}

/**
 * Filters accepted by `GET /api/v1/tickets`. Every field is optional; only supplied filters are
 * forwarded as query parameters. `page`/`pageSize` drive pagination.
 */
export interface TicketSearchFilters {
  registrationNumber?: string;
  identifierValue?: string;
  fullName?: string;
  contractNumber?: string;
  statusCode?: string;
  stageCode?: string;
  productCode?: string;
  classifierCode?: string;
  channelCode?: string;
  assigneeId?: string;
  teamId?: string;
  receivedFrom?: string;
  receivedTo?: string;
  registeredFrom?: string;
  registeredTo?: string;
  page?: number;
  pageSize?: number;
}

/** RFC 7807 Problem Details as served by the gateway (BFF `Problem`). */
export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail?: string | null;
  instance?: string | null;
}
