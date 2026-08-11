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

/** Party role on an appeal (BFF `ApplicantInput.applicantType`). */
export type ApplicantType = "CONSUMER" | "REPRESENTATIVE";

/** National-identifier kind (BFF `ApplicantInput.identifierType`). */
export type IdentifierType = "IIN" | "BIN";

/** Provenance of a party's data (BFF `ApplicantInput.dataSource`). */
export type DataSource = "APPEAL" | "CORE_SYSTEM" | "MANUAL";

/**
 * A party attached to an appeal on registration (BFF `ApplicantInput`).
 *
 * All demographic fields are optional and must never block registration (docs/01); only
 * `applicantType` and `dataSource` are required by the contract.
 */
export interface ApplicantInput {
  applicantType: ApplicantType;
  dataSource: DataSource;
  fullName?: string | null;
  identifierType?: IdentifierType | null;
  identifierValue?: string | null;
  email?: string | null;
  phone?: string | null;
  genderCode?: string | null;
  birthDate?: string | null;
  age?: number | null;
  regionCode?: string | null;
  representativeBasis?: string | null;
}

/** Request body for `POST /api/v1/tickets` (BFF `CreateTicketRequest`). */
export interface CreateTicketRequest {
  receivedAt: string;
  sourceChannelCode: string;
  subject: string;
  description: string;
  productCode: string;
  classifierCode: string;
  priorityCode: string;
  contractNumber?: string | null;
  applicant: ApplicantInput;
  representative?: ApplicantInput | null;
  isConfidential?: boolean;
}

/** A party as returned on the appeal card; the national identifier is masked (BFF `ApplicantResponse`). */
export interface ApplicantResponse {
  id: string;
  applicantType: ApplicantType;
  fullName: string | null;
  identifierType: IdentifierType | null;
  identifierMasked: string | null;
  email: string | null;
  phone: string | null;
  genderCode: string | null;
  birthDate: string | null;
  age: number | null;
  regionCode: string | null;
  dataSource: DataSource;
  representativeBasis: string | null;
}

/**
 * The full appeal card (BFF `TicketResponse`).
 *
 * Returned by registration and every card command, and carried by the workspace `ticket` section.
 * All regulatory fields (SLA deadlines, decision, closure, retention, legal hold) are projected so
 * the card view (01E-4) can render them; the decoder validates every field.
 */
export interface TicketResponse {
  id: string;
  registrationNumber: string;
  receivedAt: string;
  registeredAt: string;
  sourceChannelCode: string;
  subject: string;
  description: string;
  productCode: string;
  classifierCode: string;
  priorityCode: string;
  currentStatusCode: string;
  currentStageCode: string;
  currentTeamId: string | null;
  currentAssigneeId: string | null;
  contractNumber: string | null;
  legalDueAt: string | null;
  internalDueAt: string | null;
  slaPolicyVersion: string | null;
  decisionCode: string | null;
  decisionSummary: string | null;
  decisionText: string | null;
  decisionAt: string | null;
  decisionBy: string | null;
  closureReasonCode: string | null;
  closedAt: string | null;
  responseSentAt: string | null;
  noResponseReason: string | null;
  retentionUntil: string | null;
  legalHold: boolean;
  isConfidential: boolean;
  version: number;
  applicants: ApplicantResponse[];
}

/** A comment on an appeal (BFF `CommentResponse`). */
export interface CommentResponse {
  id: string;
  ticketId: string;
  authorId: string;
  body: string;
  createdAt: string;
}

/** Read status of an aggregated workspace section (BFF `WorkspaceSection.status`). */
export type WorkspaceSectionStatus = "ok" | "unavailable" | "not_implemented";

/**
 * A single aggregated workspace section (BFF `WorkspaceSection`).
 *
 * `data` carries the section payload only when `status` is `ok`; it is `null` otherwise. The payload
 * is left as the decoded JSON value here and narrowed by the page (the ticket section to a card, the
 * comments section to a comment list).
 */
export interface WorkspaceSection {
  status: WorkspaceSectionStatus;
  data: unknown;
}

/** The workspace sections aggregated for an appeal (BFF `WorkspaceSections`). */
export interface WorkspaceSections {
  ticket: WorkspaceSection;
  comments: WorkspaceSection;
  process: WorkspaceSection;
  mail: WorkspaceSection;
  documents: WorkspaceSection;
}

/** The aggregated appeal workspace (BFF `Workspace`). */
export interface Workspace {
  ticketId: string;
  degraded: boolean;
  sections: WorkspaceSections;
}

/** Request body for `PATCH /api/v1/tickets/{ticketId}` (BFF `UpdateTicketRequest`). */
export interface UpdateTicketRequest {
  expectedVersion: number;
  subject?: string | null;
  description?: string | null;
  sourceChannelCode?: string | null;
  contractNumber?: string | null;
}

/** Request body for `POST /api/v1/tickets/{ticketId}/classify` (BFF `ClassifyRequest`). */
export interface ClassifyRequest {
  expectedVersion: number;
  productCode: string;
  classifierCode: string;
  priorityCode: string;
}

/** Request body for `POST /api/v1/tickets/{ticketId}/decision` (BFF `RecordDecisionRequest`). */
export interface RecordDecisionRequest {
  expectedVersion: number;
  decisionCode: string;
  decisionSummary?: string | null;
  decisionText: string;
}

/** Request body for `POST /api/v1/tickets/{ticketId}/close` (BFF `CloseTicketRequest`). */
export interface CloseTicketRequest {
  expectedVersion: number;
  closureReasonCode: string;
  responseSentAt?: string | null;
  noResponseReason?: string | null;
}

/** Request body for `POST /api/v1/tickets/{ticketId}/legal-hold` (BFF `LegalHoldRequest`). */
export interface LegalHoldRequest {
  expectedVersion: number;
  legalHold: boolean;
  reason?: string | null;
}

/** Request body for `POST /api/v1/tickets/{ticketId}/comments` (BFF `CommentRequest`). */
export interface CommentRequest {
  body: string;
}

/** A single active reference-dictionary entry (BFF `ReferenceEntry`). */
export interface ReferenceEntry {
  dictionaryType: string;
  code: string;
  displayNameRu: string;
  displayNameKk: string | null;
  sortOrder: number;
}

/** The active reference-dictionary entries (BFF `ReferenceDataResponse`). */
export interface ReferenceDataResponse {
  entries: ReferenceEntry[];
}

/** RFC 7807 Problem Details as served by the gateway (BFF `Problem`). */
export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail?: string | null;
  instance?: string | null;
}
