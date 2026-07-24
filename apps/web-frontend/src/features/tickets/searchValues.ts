/**
 * Search-form value model and mapping to gateway query filters.
 *
 * The form works with plain strings (including `yyyy-mm-dd` date inputs) so it is easy to control
 * and test. `toFilters` trims blanks, widens each date to an inclusive UTC instant (lower bound at
 * start of day, upper bound at end of day) to match the gateway's `date-time` filters, and applies
 * pagination.
 */
import type { TicketSearchFilters } from "../../api/types";

/** The raw string values held by the search form. */
export interface TicketSearchFormValues {
  registrationNumber: string;
  fullName: string;
  identifierValue: string;
  contractNumber: string;
  statusCode: string;
  stageCode: string;
  productCode: string;
  classifierCode: string;
  channelCode: string;
  receivedFrom: string;
  receivedTo: string;
  registeredFrom: string;
  registeredTo: string;
}

/** An all-empty set of form values. */
export const EMPTY_FORM_VALUES: TicketSearchFormValues = {
  registrationNumber: "",
  fullName: "",
  identifierValue: "",
  contractNumber: "",
  statusCode: "",
  stageCode: "",
  productCode: "",
  classifierCode: "",
  channelCode: "",
  receivedFrom: "",
  receivedTo: "",
  registeredFrom: "",
  registeredTo: "",
};

/**
 * Trim a value and return undefined when it is blank.
 *
 * Args:
 *   value: The raw input value.
 *
 * Returns:
 *   The trimmed string, or undefined when empty.
 */
function clean(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

/**
 * Widen a `yyyy-mm-dd` date to an inclusive UTC instant.
 *
 * Args:
 *   value: The date input value.
 *   bound: Whether the value is the inclusive lower or upper bound.
 *
 * Returns:
 *   An ISO-8601 UTC timestamp, or undefined when the date is blank.
 */
function toInstant(value: string, bound: "start" | "end"): string | undefined {
  const date = clean(value);
  if (!date) {
    return undefined;
  }
  return bound === "start" ? `${date}T00:00:00Z` : `${date}T23:59:59Z`;
}

/**
 * Map form values and pagination into gateway search filters.
 *
 * Args:
 *   values: The current form values.
 *   page: The 1-based page number.
 *   pageSize: The page size.
 *
 * Returns:
 *   The filters to send to the gateway, with blank fields omitted.
 */
export function toFilters(
  values: TicketSearchFormValues,
  page: number,
  pageSize: number,
): TicketSearchFilters {
  return {
    registrationNumber: clean(values.registrationNumber),
    fullName: clean(values.fullName),
    identifierValue: clean(values.identifierValue),
    contractNumber: clean(values.contractNumber),
    statusCode: clean(values.statusCode),
    stageCode: clean(values.stageCode),
    productCode: clean(values.productCode),
    classifierCode: clean(values.classifierCode),
    channelCode: clean(values.channelCode),
    receivedFrom: toInstant(values.receivedFrom, "start"),
    receivedTo: toInstant(values.receivedTo, "end"),
    registeredFrom: toInstant(values.registeredFrom, "start"),
    registeredTo: toInstant(values.registeredTo, "end"),
    page,
    pageSize,
  };
}
