/**
 * Runtime decoders validating untrusted gateway responses and restored storage.
 *
 * The frontend never trusts `response.json() as T`. Every value that crosses the HTTP boundary (or
 * is restored from `sessionStorage`) is validated here against the committed BFF wire contract
 * (`contracts/openapi/bff-service.v1.yaml`): required/nullable fields, primitive and array element
 * types, the supported role set, and sane pagination bounds. A failure raises `ProtocolError` so
 * the caller fails closed instead of rendering malformed data or persisting an inconsistent session.
 *
 * These are hand-written transport validators, not a shared domain model (ADR-0009); they stay a
 * projection of the BFF contract.
 */
import { ProtocolError } from "./errors";
import type {
  ApplicantResponse,
  ApplicantType,
  AuthContext,
  CommentResponse,
  DataSource,
  IdentifierType,
  PageMeta,
  PaginatedTickets,
  ProblemDetails,
  ReferenceDataResponse,
  ReferenceEntry,
  Role,
  TicketResponse,
  TicketSummary,
  TokenResponse,
  Workspace,
  WorkspaceSection,
  WorkspaceSectionStatus,
} from "./types";

/** The roles the frontend accepts; any other role value fails closed. */
export const SUPPORTED_ROLES: readonly Role[] = [
  "EMPLOYEE",
  "SUPERVISOR",
  "FIRST_LINE_READONLY",
  "OMBUDSMAN",
  "ANALYST",
  "ADMIN",
  "AUDITOR",
];

/** Upper bound accepted for a page size, mirroring the BFF contract's `maximum: 100`. */
const MAX_PAGE_SIZE = 100;

/** RFC 4122 / UUIDv7-shaped identifier (any version/variant hex layout). */
const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/**
 * ISO-8601 offset-aware date-time with captured components. The structure is validated here; the
 * calendar/range correctness (month, day-in-month, leap years, time, and offset bounds) is checked
 * separately because a regex alone cannot reject impossible dates.
 */
const DATE_TIME_RE =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

/**
 * Whether a string is a UUID-formatted identifier.
 *
 * Args:
 *   value: The candidate string.
 *
 * Returns:
 *   True when the value matches the UUID layout.
 */
export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

/**
 * Number of days in a given month, honouring leap years.
 *
 * Args:
 *   year: The four-digit year.
 *   month: The 1-based month (1-12).
 *
 * Returns:
 *   The number of days in the month.
 */
function daysInMonth(year: number, month: number): number {
  // Date.UTC treats the month as 0-based; passing the 1-based month with day 0 yields the last day
  // of that 1-based month, which is the day count (leap years handled by the engine).
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/**
 * Whether a string is a real, offset-aware ISO-8601 date-time.
 *
 * Beyond the structural regex, this rejects calendar-impossible values (for example `2026-02-30`,
 * February 29 in a non-leap year, month 13, day 31 of a 30-day month) and out-of-range time and
 * offset components. Valid fractional seconds and a `Z` or numeric offset are accepted.
 *
 * Args:
 *   value: The candidate string.
 *
 * Returns:
 *   True when the value is a valid offset-aware date-time.
 */
function isValidIsoDateTime(value: string): boolean {
  const match = DATE_TIME_RE.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offset = match[7]!;

  if (month < 1 || month > 12) {
    return false;
  }
  if (day < 1 || day > daysInMonth(year, month)) {
    return false;
  }
  if (hour > 23 || minute > 59 || second > 59) {
    return false;
  }
  if (offset !== "Z") {
    const offsetHours = Number(offset.slice(1, 3));
    const offsetMinutes = Number(offset.slice(4, 6));
    if (offsetHours > 23 || offsetMinutes > 59) {
      return false;
    }
  }
  return true;
}

/** A calendar date `YYYY-MM-DD` (OpenAPI `format: date`) with captured components. */
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Whether a string is a real ISO-8601 calendar date (`YYYY-MM-DD`, no time component).
 *
 * Beyond the structural regex, this rejects calendar-impossible values (for example `2026-02-30`,
 * February 29 in a non-leap year, month 13, day 31 of a 30-day month), mirroring the date-time
 * validator so `format: date` fields are checked to the same standard.
 *
 * Args:
 *   value: The candidate string.
 *
 * Returns:
 *   True when the value is a valid calendar date.
 */
function isValidIsoDate(value: string): boolean {
  const match = DATE_RE.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12) {
    return false;
  }
  if (day < 1 || day > daysInMonth(year, month)) {
    return false;
  }
  return true;
}

/**
 * Narrow an unknown value to a plain object.
 *
 * Args:
 *   value: The value to check.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The value typed as a string-keyed record.
 *
 * Raises:
 *   ProtocolError: When the value is not a non-null, non-array object.
 */
function asObject(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ProtocolError(`${context}: expected an object`);
  }
  return value as Record<string, unknown>;
}

/**
 * Require a non-empty string field.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The string value.
 *
 * Raises:
 *   ProtocolError: When the field is missing or not a string.
 */
function requireString(source: Record<string, unknown>, key: string, context: string): string {
  const value = source[key];
  if (typeof value !== "string") {
    throw new ProtocolError(`${context}.${key}: expected a string`);
  }
  return value;
}

/**
 * Read a nullable string field (missing is treated as null).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The string value, or null when absent/null.
 *
 * Raises:
 *   ProtocolError: When present but not a string or null.
 */
function nullableString(
  source: Record<string, unknown>,
  key: string,
  context: string,
): string | null {
  const value = source[key];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string") {
    throw new ProtocolError(`${context}.${key}: expected a string or null`);
  }
  return value;
}

/**
 * Require an integer field.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The integer value.
 *
 * Raises:
 *   ProtocolError: When the field is missing or not an integer.
 */
function requireInteger(source: Record<string, unknown>, key: string, context: string): number {
  const value = source[key];
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ProtocolError(`${context}.${key}: expected an integer`);
  }
  return value;
}

/**
 * Require a boolean field.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The boolean value.
 *
 * Raises:
 *   ProtocolError: When the field is missing or not a boolean.
 */
function requireBoolean(source: Record<string, unknown>, key: string, context: string): boolean {
  const value = source[key];
  if (typeof value !== "boolean") {
    throw new ProtocolError(`${context}.${key}: expected a boolean`);
  }
  return value;
}

/**
 * Require a positive integer field (for example, a token lifetime).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The positive integer value.
 *
 * Raises:
 *   ProtocolError: When the field is missing, not an integer, or not positive.
 */
function requirePositiveInteger(
  source: Record<string, unknown>,
  key: string,
  context: string,
): number {
  const value = requireInteger(source, key, context);
  if (value <= 0) {
    throw new ProtocolError(`${context}.${key}: expected a positive integer`);
  }
  return value;
}

/**
 * Require a UUID-formatted string field.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The UUID string.
 *
 * Raises:
 *   ProtocolError: When the field is missing or not a UUID.
 */
function requireUuid(source: Record<string, unknown>, key: string, context: string): string {
  const value = requireString(source, key, context);
  if (!UUID_RE.test(value)) {
    throw new ProtocolError(`${context}.${key}: expected a UUID`);
  }
  return value;
}

/**
 * Read a nullable UUID-formatted string field (missing is treated as null).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The UUID string, or null when absent/null.
 *
 * Raises:
 *   ProtocolError: When present but not a UUID.
 */
function nullableUuid(
  source: Record<string, unknown>,
  key: string,
  context: string,
): string | null {
  const value = nullableString(source, key, context);
  if (value !== null && !UUID_RE.test(value)) {
    throw new ProtocolError(`${context}.${key}: expected a UUID or null`);
  }
  return value;
}

/**
 * Require an ISO-8601 offset-aware date-time string field.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The date-time string.
 *
 * Raises:
 *   ProtocolError: When the field is missing, malformed, or not a real instant.
 */
function requireDateTime(source: Record<string, unknown>, key: string, context: string): string {
  const value = requireString(source, key, context);
  if (!isValidIsoDateTime(value)) {
    throw new ProtocolError(`${context}.${key}: expected an ISO-8601 date-time`);
  }
  return value;
}

/**
 * Read a nullable ISO-8601 offset-aware date-time field (missing is treated as null).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The date-time string, or null when absent/null.
 *
 * Raises:
 *   ProtocolError: When present but not a real instant.
 */
function nullableDateTime(
  source: Record<string, unknown>,
  key: string,
  context: string,
): string | null {
  const value = nullableString(source, key, context);
  if (value !== null && !isValidIsoDateTime(value)) {
    throw new ProtocolError(`${context}.${key}: expected an ISO-8601 date-time or null`);
  }
  return value;
}

/**
 * Read a nullable ISO-8601 calendar-date field (`format: date`; missing is treated as null).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The date string, or null when absent/null.
 *
 * Raises:
 *   ProtocolError: When present but not a real calendar date.
 */
function nullableDate(
  source: Record<string, unknown>,
  key: string,
  context: string,
): string | null {
  const value = nullableString(source, key, context);
  if (value !== null && !isValidIsoDate(value)) {
    throw new ProtocolError(`${context}.${key}: expected an ISO-8601 date or null`);
  }
  return value;
}

/**
 * Read a nullable integer field (missing is treated as null).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The integer value, or null when absent/null.
 *
 * Raises:
 *   ProtocolError: When present but not an integer.
 */
function nullableInteger(
  source: Record<string, unknown>,
  key: string,
  context: string,
): number | null {
  const value = source[key];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ProtocolError(`${context}.${key}: expected an integer or null`);
  }
  return value;
}

/**
 * Require a string field constrained to a fixed set of allowed values.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   allowed: The permitted values.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The value, narrowed to the allowed union.
 *
 * Raises:
 *   ProtocolError: When the field is missing or not one of the allowed values.
 */
function requireEnum<T extends string>(
  source: Record<string, unknown>,
  key: string,
  allowed: readonly T[],
  context: string,
): T {
  const value = requireString(source, key, context);
  if (!allowed.includes(value as T)) {
    throw new ProtocolError(`${context}.${key}: unexpected value`);
  }
  return value as T;
}

/**
 * Read a nullable enum field (missing is treated as null).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   allowed: The permitted values.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The value narrowed to the allowed union, or null when absent/null.
 *
 * Raises:
 *   ProtocolError: When present but not one of the allowed values.
 */
function nullableEnum<T extends string>(
  source: Record<string, unknown>,
  key: string,
  allowed: readonly T[],
  context: string,
): T | null {
  const value = nullableString(source, key, context);
  if (value === null) {
    return null;
  }
  if (!allowed.includes(value as T)) {
    throw new ProtocolError(`${context}.${key}: unexpected value`);
  }
  return value as T;
}

/** Party roles accepted on an appeal card (BFF `ApplicantResponse.applicantType`). */
const APPLICANT_TYPES: readonly ApplicantType[] = ["CONSUMER", "REPRESENTATIVE"];

/** Identifier kinds accepted on an appeal card (BFF `ApplicantResponse.identifierType`). */
const IDENTIFIER_TYPES: readonly IdentifierType[] = ["IIN", "BIN"];

/** Data-provenance values accepted on an appeal card (BFF `ApplicantResponse.dataSource`). */
const DATA_SOURCES: readonly DataSource[] = ["APPEAL", "CORE_SYSTEM", "MANUAL"];

/**
 * Require an array of UUID-formatted strings.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The array of UUID strings.
 *
 * Raises:
 *   ProtocolError: When the field is not an array of UUIDs.
 */
function requireUuidArray(source: Record<string, unknown>, key: string, context: string): string[] {
  const values = requireStringArray(source, key, context);
  for (const value of values) {
    if (!UUID_RE.test(value)) {
      throw new ProtocolError(`${context}.${key}: expected an array of UUIDs`);
    }
  }
  return values;
}

/**
 * Require an array of strings.
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The array of strings.
 *
 * Raises:
 *   ProtocolError: When the field is not an array of strings.
 */
function requireStringArray(
  source: Record<string, unknown>,
  key: string,
  context: string,
): string[] {
  const value = source[key];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new ProtocolError(`${context}.${key}: expected an array of strings`);
  }
  return value as string[];
}

/**
 * Validate a role array against the supported set (fail closed on any unknown role).
 *
 * Args:
 *   source: The parent object.
 *   key: The field name.
 *   context: A short label used in the error message.
 *
 * Returns:
 *   The validated roles.
 *
 * Raises:
 *   ProtocolError: When any element is not a supported role.
 */
function requireRoles(source: Record<string, unknown>, key: string, context: string): Role[] {
  const raw = requireStringArray(source, key, context);
  for (const role of raw) {
    if (!SUPPORTED_ROLES.includes(role as Role)) {
      throw new ProtocolError(`${context}.${key}: unsupported role`);
    }
  }
  return raw as Role[];
}

/**
 * Validate a login token response (BFF `TokenResponse`).
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated token response.
 *
 * Raises:
 *   ProtocolError: When the body does not match the contract or carries an unknown role.
 */
export function decodeTokenResponse(raw: unknown): TokenResponse {
  const obj = asObject(raw, "TokenResponse");
  const tokenType = requireString(obj, "tokenType", "TokenResponse");
  if (tokenType !== "Bearer") {
    throw new ProtocolError("TokenResponse.tokenType: expected 'Bearer'");
  }
  return {
    accessToken: requireString(obj, "accessToken", "TokenResponse"),
    tokenType: "Bearer",
    expiresIn: requirePositiveInteger(obj, "expiresIn", "TokenResponse"),
    subject: requireUuid(obj, "subject", "TokenResponse"),
    username: requireString(obj, "username", "TokenResponse"),
    roles: requireRoles(obj, "roles", "TokenResponse"),
    permissions: requireStringArray(obj, "permissions", "TokenResponse"),
    teams: requireUuidArray(obj, "teams", "TokenResponse"),
  };
}

/**
 * Validate a resolved auth context (BFF `AuthContext`).
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated auth context.
 *
 * Raises:
 *   ProtocolError: When the body does not match the contract.
 */
export function decodeAuthContext(raw: unknown): AuthContext {
  const obj = asObject(raw, "AuthContext");
  return {
    subject: requireUuid(obj, "subject", "AuthContext"),
    username: requireString(obj, "username", "AuthContext"),
    roles: requireStringArray(obj, "roles", "AuthContext"),
    permissions: requireStringArray(obj, "permissions", "AuthContext"),
  };
}

/**
 * Validate a compact appeal summary (BFF `TicketSummary`).
 *
 * Args:
 *   raw: The parsed JSON item.
 *
 * Returns:
 *   The validated summary.
 *
 * Raises:
 *   ProtocolError: When the item does not match the contract.
 */
export function decodeTicketSummary(raw: unknown): TicketSummary {
  const obj = asObject(raw, "TicketSummary");
  return {
    id: requireUuid(obj, "id", "TicketSummary"),
    registrationNumber: requireString(obj, "registrationNumber", "TicketSummary"),
    subject: requireString(obj, "subject", "TicketSummary"),
    currentStatusCode: requireString(obj, "currentStatusCode", "TicketSummary"),
    currentStageCode: requireString(obj, "currentStageCode", "TicketSummary"),
    productCode: requireString(obj, "productCode", "TicketSummary"),
    classifierCode: requireString(obj, "classifierCode", "TicketSummary"),
    priorityCode: requireString(obj, "priorityCode", "TicketSummary"),
    contractNumber: nullableString(obj, "contractNumber", "TicketSummary"),
    currentAssigneeId: nullableUuid(obj, "currentAssigneeId", "TicketSummary"),
    currentTeamId: nullableUuid(obj, "currentTeamId", "TicketSummary"),
    receivedAt: requireDateTime(obj, "receivedAt", "TicketSummary"),
    registeredAt: requireDateTime(obj, "registeredAt", "TicketSummary"),
  };
}

/**
 * Validate pagination metadata (BFF `PageMeta`) with sane bounds.
 *
 * Args:
 *   raw: The parsed JSON object.
 *
 * Returns:
 *   The validated page metadata.
 *
 * Raises:
 *   ProtocolError: When a field is missing, mistyped, or out of bounds.
 */
export function decodePageMeta(raw: unknown): PageMeta {
  const obj = asObject(raw, "PageMeta");
  const page = requireInteger(obj, "page", "PageMeta");
  const pageSize = requireInteger(obj, "pageSize", "PageMeta");
  const total = requireInteger(obj, "total", "PageMeta");
  if (page < 1 || pageSize < 1 || pageSize > MAX_PAGE_SIZE || total < 0) {
    throw new ProtocolError("PageMeta: values out of bounds");
  }
  return { page, pageSize, total };
}

/**
 * Validate a page of appeals (BFF `PaginatedTickets`).
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated paginated result.
 *
 * Raises:
 *   ProtocolError: When the envelope or any item does not match the contract.
 */
export function decodePaginatedTickets(raw: unknown): PaginatedTickets {
  const obj = asObject(raw, "PaginatedTickets");
  const items = obj.items;
  if (!Array.isArray(items)) {
    throw new ProtocolError("PaginatedTickets.items: expected an array");
  }
  return {
    items: items.map(decodeTicketSummary),
    page: decodePageMeta(obj.page),
  };
}

/**
 * Validate a single reference-dictionary entry (BFF `ReferenceEntry`).
 *
 * Args:
 *   raw: The parsed JSON item.
 *
 * Returns:
 *   The validated reference entry.
 *
 * Raises:
 *   ProtocolError: When the item does not match the contract.
 */
export function decodeReferenceEntry(raw: unknown): ReferenceEntry {
  const obj = asObject(raw, "ReferenceEntry");
  return {
    dictionaryType: requireString(obj, "dictionaryType", "ReferenceEntry"),
    code: requireString(obj, "code", "ReferenceEntry"),
    displayNameRu: requireString(obj, "displayNameRu", "ReferenceEntry"),
    displayNameKk: nullableString(obj, "displayNameKk", "ReferenceEntry"),
    sortOrder: requireInteger(obj, "sortOrder", "ReferenceEntry"),
  };
}

/**
 * Validate the reference-data response envelope (BFF `ReferenceDataResponse`).
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated reference-data response.
 *
 * Raises:
 *   ProtocolError: When the envelope or any entry does not match the contract.
 */
export function decodeReferenceData(raw: unknown): ReferenceDataResponse {
  const obj = asObject(raw, "ReferenceDataResponse");
  const entries = obj.entries;
  if (!Array.isArray(entries)) {
    throw new ProtocolError("ReferenceDataResponse.entries: expected an array");
  }
  return { entries: entries.map(decodeReferenceEntry) };
}

/**
 * Validate a party attached to an appeal card (BFF `ApplicantResponse`).
 *
 * The national identifier only ever crosses the wire masked (`identifierMasked`); the raw value is
 * never present in a response.
 *
 * Args:
 *   raw: The parsed JSON item.
 *
 * Returns:
 *   The validated applicant.
 *
 * Raises:
 *   ProtocolError: When the item does not match the contract.
 */
export function decodeApplicant(raw: unknown): ApplicantResponse {
  const obj = asObject(raw, "ApplicantResponse");
  return {
    id: requireUuid(obj, "id", "ApplicantResponse"),
    applicantType: requireEnum(obj, "applicantType", APPLICANT_TYPES, "ApplicantResponse"),
    fullName: nullableString(obj, "fullName", "ApplicantResponse"),
    identifierType: nullableEnum(obj, "identifierType", IDENTIFIER_TYPES, "ApplicantResponse"),
    identifierMasked: nullableString(obj, "identifierMasked", "ApplicantResponse"),
    email: nullableString(obj, "email", "ApplicantResponse"),
    phone: nullableString(obj, "phone", "ApplicantResponse"),
    genderCode: nullableString(obj, "genderCode", "ApplicantResponse"),
    birthDate: nullableDate(obj, "birthDate", "ApplicantResponse"),
    age: nullableInteger(obj, "age", "ApplicantResponse"),
    regionCode: nullableString(obj, "regionCode", "ApplicantResponse"),
    dataSource: requireEnum(obj, "dataSource", DATA_SOURCES, "ApplicantResponse"),
    representativeBasis: nullableString(obj, "representativeBasis", "ApplicantResponse"),
  };
}

/**
 * Validate the full appeal card (BFF `TicketResponse`).
 *
 * Returned by registration and every card command, and carried by the workspace `ticket` section.
 * Every field the card view renders is validated; a violation fails closed rather than rendering
 * malformed regulatory data.
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated appeal card.
 *
 * Raises:
 *   ProtocolError: When the body does not match the contract.
 */
export function decodeTicketResponse(raw: unknown): TicketResponse {
  const obj = asObject(raw, "TicketResponse");
  const applicants = obj.applicants;
  if (!Array.isArray(applicants)) {
    throw new ProtocolError("TicketResponse.applicants: expected an array");
  }
  return {
    id: requireUuid(obj, "id", "TicketResponse"),
    registrationNumber: requireString(obj, "registrationNumber", "TicketResponse"),
    receivedAt: requireDateTime(obj, "receivedAt", "TicketResponse"),
    registeredAt: requireDateTime(obj, "registeredAt", "TicketResponse"),
    sourceChannelCode: requireString(obj, "sourceChannelCode", "TicketResponse"),
    subject: requireString(obj, "subject", "TicketResponse"),
    description: requireString(obj, "description", "TicketResponse"),
    productCode: requireString(obj, "productCode", "TicketResponse"),
    classifierCode: requireString(obj, "classifierCode", "TicketResponse"),
    priorityCode: requireString(obj, "priorityCode", "TicketResponse"),
    currentStatusCode: requireString(obj, "currentStatusCode", "TicketResponse"),
    currentStageCode: requireString(obj, "currentStageCode", "TicketResponse"),
    currentTeamId: nullableUuid(obj, "currentTeamId", "TicketResponse"),
    currentAssigneeId: nullableUuid(obj, "currentAssigneeId", "TicketResponse"),
    contractNumber: nullableString(obj, "contractNumber", "TicketResponse"),
    legalDueAt: nullableDateTime(obj, "legalDueAt", "TicketResponse"),
    internalDueAt: nullableDateTime(obj, "internalDueAt", "TicketResponse"),
    slaPolicyVersion: nullableString(obj, "slaPolicyVersion", "TicketResponse"),
    decisionCode: nullableString(obj, "decisionCode", "TicketResponse"),
    decisionSummary: nullableString(obj, "decisionSummary", "TicketResponse"),
    decisionText: nullableString(obj, "decisionText", "TicketResponse"),
    decisionAt: nullableDateTime(obj, "decisionAt", "TicketResponse"),
    decisionBy: nullableUuid(obj, "decisionBy", "TicketResponse"),
    closureReasonCode: nullableString(obj, "closureReasonCode", "TicketResponse"),
    closedAt: nullableDateTime(obj, "closedAt", "TicketResponse"),
    responseSentAt: nullableDateTime(obj, "responseSentAt", "TicketResponse"),
    noResponseReason: nullableString(obj, "noResponseReason", "TicketResponse"),
    retentionUntil: nullableDate(obj, "retentionUntil", "TicketResponse"),
    legalHold: requireBoolean(obj, "legalHold", "TicketResponse"),
    isConfidential: requireBoolean(obj, "isConfidential", "TicketResponse"),
    version: requireInteger(obj, "version", "TicketResponse"),
    applicants: applicants.map(decodeApplicant),
  };
}

/**
 * Validate a single appeal comment (BFF `CommentResponse`).
 *
 * Args:
 *   raw: The parsed JSON item.
 *
 * Returns:
 *   The validated comment.
 *
 * Raises:
 *   ProtocolError: When the item does not match the contract.
 */
export function decodeComment(raw: unknown): CommentResponse {
  const obj = asObject(raw, "CommentResponse");
  return {
    id: requireUuid(obj, "id", "CommentResponse"),
    ticketId: requireUuid(obj, "ticketId", "CommentResponse"),
    authorId: requireUuid(obj, "authorId", "CommentResponse"),
    body: requireString(obj, "body", "CommentResponse"),
    createdAt: requireDateTime(obj, "createdAt", "CommentResponse"),
  };
}

/**
 * Validate a list of appeal comments.
 *
 * The workspace comments section carries a bare JSON array (not an envelope), so this validates the
 * array itself and each element.
 *
 * Args:
 *   raw: The parsed JSON value.
 *
 * Returns:
 *   The validated comments, in the order returned.
 *
 * Raises:
 *   ProtocolError: When the value is not an array or any element is invalid.
 */
export function decodeCommentList(raw: unknown): CommentResponse[] {
  if (!Array.isArray(raw)) {
    throw new ProtocolError("CommentList: expected an array");
  }
  return raw.map(decodeComment);
}

/** Read statuses accepted for a workspace section (BFF `WorkspaceSection.status`). */
const SECTION_STATUSES: readonly WorkspaceSectionStatus[] = [
  "ok",
  "unavailable",
  "not_implemented",
];

/**
 * Validate a single workspace section (BFF `WorkspaceSection`).
 *
 * The `data` payload is left as the decoded JSON value; the page narrows it (card or comment list)
 * only for an `ok` section. A non-`ok` section must carry null data.
 *
 * Args:
 *   raw: The parsed JSON object.
 *
 * Returns:
 *   The validated section.
 *
 * Raises:
 *   ProtocolError: When the object does not match the contract.
 */
function decodeWorkspaceSection(raw: unknown, context: string): WorkspaceSection {
  const obj = asObject(raw, context);
  const status = requireEnum(obj, "status", SECTION_STATUSES, context);
  // `data` is a required field in the contract (nullable, not optional): a section missing it is a
  // malformed response and must fail closed, not be silently coerced to null.
  if (!("data" in obj)) {
    throw new ProtocolError(`${context}.data: required field is missing`);
  }
  const data = obj.data ?? null;
  if (status !== "ok" && data !== null) {
    throw new ProtocolError(`${context}.data: expected null for a non-ok section`);
  }
  return { status, data };
}

/**
 * Validate the aggregated appeal workspace (BFF `Workspace`).
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated workspace envelope.
 *
 * Raises:
 *   ProtocolError: When the envelope or any section does not match the contract.
 */
export function decodeWorkspace(raw: unknown): Workspace {
  const obj = asObject(raw, "Workspace");
  const sections = asObject(obj.sections, "Workspace.sections");
  return {
    ticketId: requireUuid(obj, "ticketId", "Workspace"),
    degraded: requireBoolean(obj, "degraded", "Workspace"),
    sections: {
      ticket: decodeWorkspaceSection(sections.ticket, "Workspace.sections.ticket"),
      comments: decodeWorkspaceSection(sections.comments, "Workspace.sections.comments"),
      process: decodeWorkspaceSection(sections.process, "Workspace.sections.process"),
      mail: decodeWorkspaceSection(sections.mail, "Workspace.sections.mail"),
      documents: decodeWorkspaceSection(sections.documents, "Workspace.sections.documents"),
    },
  };
}

/**
 * Validate an RFC 7807 problem body, tolerating the optional fields.
 *
 * Args:
 *   raw: The parsed JSON body.
 *
 * Returns:
 *   The validated problem, or null when it is not a valid problem document.
 */
export function decodeProblem(raw: unknown): ProblemDetails | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return null;
  }
  const obj = raw as Record<string, unknown>;
  if (typeof obj.title !== "string" || typeof obj.status !== "number") {
    return null;
  }
  return {
    type: typeof obj.type === "string" ? obj.type : undefined,
    title: obj.title,
    status: obj.status,
    detail: typeof obj.detail === "string" ? obj.detail : null,
    instance: typeof obj.instance === "string" ? obj.instance : null,
  };
}
