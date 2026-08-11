/**
 * Value models, validation, and request mapping for the appeal-card commands.
 *
 * The card forms (edit details, re-classify, record decision, close) work with plain strings so they
 * are easy to control and test. Each builder validates the fields the gateway/Ticket Service require
 * and, when valid, maps them to the transport request carrying the caller-provided `expectedVersion`
 * for optimistic locking. Client-side validation mirrors the regulatory rules (a decision needs code
 * and text; a closure needs a reason and either a response date or a recorded reason for its absence,
 * docs/01) so the operator gets immediate feedback, while the Ticket Service remains the authority.
 */
import type {
  ClassifyRequest,
  CloseTicketRequest,
  RecordDecisionRequest,
  UpdateTicketRequest,
} from "../../api/types";
import { localDateTimeToIsoInstant } from "../../lib/dateTime";

/** A validation error code per field; the page maps it to a localized message. */
export type CardErrorCode = "required" | "invalidDateTime" | "responseOrReason" | "noChanges";

/** Field-path → error-code map (empty when the form is valid). */
export type CardErrors = Record<string, CardErrorCode>;

/**
 * Trim a value and return null when it is blank.
 *
 * Args:
 *   value: The raw input value.
 *
 * Returns:
 *   The trimmed string, or null when empty.
 */
function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** Editable appeal-card detail values (mirrors `UpdateTicketRequest`, minus the version). */
export interface EditFormValues {
  subject: string;
  description: string;
  sourceChannelCode: string;
  contractNumber: string;
}

/** Classification values (mirrors `ClassifyRequest`, minus the version). */
export interface ClassifyFormValues {
  productCode: string;
  classifierCode: string;
  priorityCode: string;
}

/** Decision values (mirrors `RecordDecisionRequest`, minus the version). */
export interface DecisionFormValues {
  decisionCode: string;
  decisionSummary: string;
  decisionText: string;
}

/** Closure values (mirrors `CloseTicketRequest`, minus the version). */
export interface CloseFormValues {
  closureReasonCode: string;
  responseSentAt: string;
  noResponseReason: string;
}

/**
 * Validate the edit form and, when valid and changed, build the partial update request.
 *
 * Only fields that differ from the original card are included, so the PATCH carries the minimal
 * change (an unchanged form is rejected with a `noChanges` marker rather than sending an empty
 * update). The subject, description, and intake channel are required on the card, so blanking them is
 * an error; the contract number is optional and a blank value clears it (sent as null).
 *
 * Args:
 *   values: The current edit values.
 *   original: The values as loaded from the card, used to compute the changed set.
 *   expectedVersion: The version the client last observed (optimistic locking).
 *
 * Returns:
 *   An object with the validation errors (empty when valid) and the request (null when invalid or
 *   unchanged).
 */
export function buildUpdateRequest(
  values: EditFormValues,
  original: EditFormValues,
  expectedVersion: number,
): { errors: CardErrors; request: UpdateTicketRequest | null } {
  const errors: CardErrors = {};
  for (const field of ["subject", "description", "sourceChannelCode"] as const) {
    if (values[field].trim() === "") {
      errors[field] = "required";
    }
  }
  if (Object.keys(errors).length > 0) {
    return { errors, request: null };
  }

  const request: UpdateTicketRequest = { expectedVersion };
  let changed = false;
  if (values.subject.trim() !== original.subject.trim()) {
    request.subject = values.subject.trim();
    changed = true;
  }
  if (values.description.trim() !== original.description.trim()) {
    request.description = values.description.trim();
    changed = true;
  }
  if (values.sourceChannelCode.trim() !== original.sourceChannelCode.trim()) {
    request.sourceChannelCode = values.sourceChannelCode.trim();
    changed = true;
  }
  const nextContract = trimmedOrNull(values.contractNumber);
  if (nextContract !== trimmedOrNull(original.contractNumber)) {
    request.contractNumber = nextContract;
    changed = true;
  }
  if (!changed) {
    return { errors: { form: "noChanges" }, request: null };
  }
  return { errors, request };
}

/**
 * Validate the classification form and, when valid, build the classify request.
 *
 * Args:
 *   values: The current classification values.
 *   expectedVersion: The version the client last observed (optimistic locking).
 *
 * Returns:
 *   An object with the validation errors (empty when valid) and the request (null when invalid).
 */
export function buildClassifyRequest(
  values: ClassifyFormValues,
  expectedVersion: number,
): { errors: CardErrors; request: ClassifyRequest | null } {
  const errors: CardErrors = {};
  for (const field of ["productCode", "classifierCode", "priorityCode"] as const) {
    if (values[field].trim() === "") {
      errors[field] = "required";
    }
  }
  if (Object.keys(errors).length > 0) {
    return { errors, request: null };
  }
  return {
    errors,
    request: {
      expectedVersion,
      productCode: values.productCode.trim(),
      classifierCode: values.classifierCode.trim(),
      priorityCode: values.priorityCode.trim(),
    },
  };
}

/**
 * Validate the decision form and, when valid, build the decision request.
 *
 * A decision requires a code and full text; the summary is optional and sent as null when blank.
 *
 * Args:
 *   values: The current decision values.
 *   expectedVersion: The version the client last observed (optimistic locking).
 *
 * Returns:
 *   An object with the validation errors (empty when valid) and the request (null when invalid).
 */
export function buildDecisionRequest(
  values: DecisionFormValues,
  expectedVersion: number,
): { errors: CardErrors; request: RecordDecisionRequest | null } {
  const errors: CardErrors = {};
  if (values.decisionCode.trim() === "") {
    errors.decisionCode = "required";
  }
  if (values.decisionText.trim() === "") {
    errors.decisionText = "required";
  }
  if (Object.keys(errors).length > 0) {
    return { errors, request: null };
  }
  return {
    errors,
    request: {
      expectedVersion,
      decisionCode: values.decisionCode.trim(),
      decisionSummary: trimmedOrNull(values.decisionSummary),
      decisionText: values.decisionText.trim(),
    },
  };
}

/**
 * Validate the close form and, when valid, build the close request.
 *
 * A closure requires a reason code and either a valid response date or a recorded reason for the
 * absence of a response (docs/01). A provided but calendar-impossible response date is rejected. The
 * Ticket Service additionally enforces that a decision was recorded first.
 *
 * Args:
 *   values: The current closure values.
 *   expectedVersion: The version the client last observed (optimistic locking).
 *
 * Returns:
 *   An object with the validation errors (empty when valid) and the request (null when invalid).
 */
export function buildCloseRequest(
  values: CloseFormValues,
  expectedVersion: number,
): { errors: CardErrors; request: CloseTicketRequest | null } {
  const errors: CardErrors = {};
  if (values.closureReasonCode.trim() === "") {
    errors.closureReasonCode = "required";
  }
  const hasResponseInput = values.responseSentAt.trim() !== "";
  const responseInstant = localDateTimeToIsoInstant(values.responseSentAt);
  if (hasResponseInput && responseInstant === null) {
    errors.responseSentAt = "invalidDateTime";
  }
  const noResponseReason = trimmedOrNull(values.noResponseReason);
  // A response date or a recorded reason for its absence is required; a blank/invalid date with no
  // recorded reason is rejected before submission.
  if (responseInstant === null && noResponseReason === null) {
    errors.response = "responseOrReason";
  }
  if (Object.keys(errors).length > 0) {
    return { errors, request: null };
  }
  return {
    errors,
    request: {
      expectedVersion,
      closureReasonCode: values.closureReasonCode.trim(),
      responseSentAt: responseInstant,
      noResponseReason,
    },
  };
}
