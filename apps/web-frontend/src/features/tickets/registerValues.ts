/**
 * Registration-form value model, validation, and mapping to the gateway create request.
 *
 * The form works with plain strings and booleans so it is easy to control and test. Required fields
 * are validated client-side before submission; every demographic field is optional and, when left
 * blank, is sent as `null` (or omitted) — the regulatory "conditional fields are nullable" rule
 * (docs/01, DoD 01E-3). The primary party is always the consumer and an optional representative is
 * the representative; the gateway enforces the same party-role invariant.
 */
import type {
  ApplicantInput,
  CreateTicketRequest,
  DataSource,
  IdentifierType,
} from "../../api/types";

/** The string/boolean values held for one party (consumer or representative). */
export interface ApplicantFormValues {
  dataSource: DataSource;
  fullName: string;
  identifierType: "" | IdentifierType;
  identifierValue: string;
  email: string;
  phone: string;
  genderCode: string;
  birthDate: string;
  age: string;
  regionCode: string;
  representativeBasis: string;
}

/** The full registration form's values. */
export interface RegisterFormValues {
  receivedAt: string;
  sourceChannelCode: string;
  subject: string;
  description: string;
  productCode: string;
  classifierCode: string;
  priorityCode: string;
  contractNumber: string;
  isConfidential: boolean;
  applicant: ApplicantFormValues;
  includeRepresentative: boolean;
  representative: ApplicantFormValues;
}

/** A validation error code per field; the page maps it to a localized message. */
export type RegisterErrorCode = "required" | "invalidAge" | "invalidReceivedAt" | "identifierPair";

/** Field-path → error-code map (empty when the form is valid). */
export type RegisterErrors = Record<string, RegisterErrorCode>;

/** An empty party with the manual-entry default provenance. */
export const EMPTY_APPLICANT: ApplicantFormValues = {
  dataSource: "MANUAL",
  fullName: "",
  identifierType: "",
  identifierValue: "",
  email: "",
  phone: "",
  genderCode: "",
  birthDate: "",
  age: "",
  regionCode: "",
  representativeBasis: "",
};

/** An all-empty set of registration values. */
export const EMPTY_REGISTER_VALUES: RegisterFormValues = {
  receivedAt: "",
  sourceChannelCode: "",
  subject: "",
  description: "",
  productCode: "",
  classifierCode: "",
  priorityCode: "",
  contractNumber: "",
  isConfidential: false,
  applicant: { ...EMPTY_APPLICANT },
  includeRepresentative: false,
  representative: { ...EMPTY_APPLICANT },
};

/** Required top-level string fields, keyed by their form field path. */
const REQUIRED_TOP_FIELDS: Array<keyof RegisterFormValues> = [
  "receivedAt",
  "sourceChannelCode",
  "subject",
  "description",
  "productCode",
  "classifierCode",
  "priorityCode",
];

/**
 * Trim a value and return null when it is blank.
 *
 * Args:
 *   value: The raw input value.
 *
 * Returns:
 *   The trimmed string, or null when empty.
 */
function cleanOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * Whether an age string is a valid non-negative integer within a sane human range.
 *
 * Args:
 *   value: The trimmed age string (already known to be non-empty).
 *
 * Returns:
 *   True when the value is an integer in [0, 150].
 */
function isValidAge(value: string): boolean {
  if (!/^\d+$/.test(value)) {
    return false;
  }
  const age = Number(value);
  return Number.isInteger(age) && age >= 0 && age <= 150;
}

/** A `datetime-local` value with captured components (`yyyy-mm-ddThh:mm`, seconds optional). */
const LOCAL_DATE_TIME_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/;

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
  // Date.UTC treats the month as 0-based; day 0 of the 1-based month yields that month's last day.
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/**
 * Convert a `datetime-local` value (local wall-clock) to an ISO-8601 UTC instant.
 *
 * A calendar-impossible value is rejected rather than accepted: `new Date("2026-02-30T09:00")` does
 * not fail — JavaScript silently rolls it over to 2026-03-02 — so parsing via `Date` alone would
 * register a different received date than the operator entered. The components are validated against
 * the real calendar (month, day-in-month with leap years, and time ranges) before a `Date` is built.
 *
 * Args:
 *   value: The `yyyy-mm-ddThh:mm` (seconds optional) input value.
 *
 * Returns:
 *   The ISO-8601 UTC timestamp, or null when the value is blank or not a real instant.
 */
function toReceivedAtInstant(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") {
    return null;
  }
  const match = LOCAL_DATE_TIME_RE.exec(trimmed);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = match[6] === undefined ? 0 : Number(match[6]);
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)) {
    return null;
  }
  if (hour > 23 || minute > 59 || second > 59) {
    return null;
  }
  const instant = new Date(year, month - 1, day, hour, minute, second);
  // Round-trip guard against the values JavaScript's Date silently shifts rather than rejects:
  // two-digit years mapped into 1900-1999 (0099 -> 1999), and local wall-clock times that do not
  // exist on a DST spring-forward boundary (rolled forward one hour). If any component fails to
  // round-trip, the instant that would be sent is not the one the operator entered, so reject it.
  if (
    instant.getFullYear() !== year ||
    instant.getMonth() !== month - 1 ||
    instant.getDate() !== day ||
    instant.getHours() !== hour ||
    instant.getMinutes() !== minute ||
    instant.getSeconds() !== second
  ) {
    return null;
  }
  return instant.toISOString();
}

/**
 * Validate one party's optional fields, collecting errors under a field-path prefix.
 *
 * Only cross-field consistency is enforced here (an identifier value needs a matching type and vice
 * versa) and a numeric age; every field remains individually optional.
 *
 * Args:
 *   party: The party values.
 *   prefix: The field-path prefix (`applicant` or `representative`).
 *   errors: The accumulating error map, mutated in place.
 */
function validateParty(party: ApplicantFormValues, prefix: string, errors: RegisterErrors): void {
  const age = party.age.trim();
  if (age !== "" && !isValidAge(age)) {
    errors[`${prefix}.age`] = "invalidAge";
  }
  const hasType = party.identifierType !== "";
  const hasValue = party.identifierValue.trim() !== "";
  if (hasType !== hasValue) {
    // An identifier is meaningful only as a (type, value) pair; require both or neither.
    errors[`${prefix}.identifierValue`] = "identifierPair";
  }
}

/**
 * Map one party's form values to the gateway applicant input.
 *
 * Args:
 *   party: The party values.
 *   applicantType: The fixed role of this party.
 *
 * Returns:
 *   The applicant input with blank optional fields sent as null.
 */
function toApplicantInput(
  party: ApplicantFormValues,
  applicantType: ApplicantInput["applicantType"],
): ApplicantInput {
  const ageValue = party.age.trim();
  return {
    applicantType,
    dataSource: party.dataSource,
    fullName: cleanOrNull(party.fullName),
    identifierType: party.identifierType === "" ? null : party.identifierType,
    identifierValue: cleanOrNull(party.identifierValue),
    email: cleanOrNull(party.email),
    phone: cleanOrNull(party.phone),
    genderCode: cleanOrNull(party.genderCode),
    birthDate: cleanOrNull(party.birthDate),
    age: ageValue === "" ? null : Number(ageValue),
    regionCode: cleanOrNull(party.regionCode),
    representativeBasis:
      applicantType === "REPRESENTATIVE" ? cleanOrNull(party.representativeBasis) : null,
  };
}

/**
 * Validate the form and, when valid, build the gateway create request.
 *
 * Args:
 *   values: The current form values.
 *
 * Returns:
 *   An object with the validation errors (empty when valid) and the request (null when invalid).
 */
export function buildCreateRequest(values: RegisterFormValues): {
  errors: RegisterErrors;
  request: CreateTicketRequest | null;
} {
  const errors: RegisterErrors = {};

  for (const field of REQUIRED_TOP_FIELDS) {
    if (String(values[field]).trim() === "") {
      errors[field] = "required";
    }
  }
  const receivedAt = toReceivedAtInstant(values.receivedAt);
  if (values.receivedAt.trim() !== "" && receivedAt === null) {
    errors.receivedAt = "invalidReceivedAt";
  }

  validateParty(values.applicant, "applicant", errors);
  if (values.includeRepresentative) {
    validateParty(values.representative, "representative", errors);
  }

  if (Object.keys(errors).length > 0 || receivedAt === null) {
    return { errors, request: null };
  }

  const request: CreateTicketRequest = {
    receivedAt,
    sourceChannelCode: values.sourceChannelCode.trim(),
    subject: values.subject.trim(),
    description: values.description.trim(),
    productCode: values.productCode.trim(),
    classifierCode: values.classifierCode.trim(),
    priorityCode: values.priorityCode.trim(),
    contractNumber: cleanOrNull(values.contractNumber),
    applicant: toApplicantInput(values.applicant, "CONSUMER"),
    representative: values.includeRepresentative
      ? toApplicantInput(values.representative, "REPRESENTATIVE")
      : null,
    isConfidential: values.isConfidential,
  };
  return { errors, request };
}
