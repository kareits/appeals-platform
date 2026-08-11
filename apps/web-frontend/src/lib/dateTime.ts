/**
 * Shared conversion from an `<input type="datetime-local">` value to an ISO-8601 UTC instant.
 *
 * Several forms (registration, closure) collect a wall-clock date-time and must send an ISO UTC
 * instant to the gateway. This module owns the one calendar-correct conversion so every form rejects
 * the same impossible inputs rather than silently shifting them.
 */

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
 * register a different instant than the operator entered. The components are validated against the
 * real calendar (month, day-in-month with leap years, and time ranges) before a `Date` is built, and
 * a round-trip guard rejects the values `Date` silently shifts (two-digit years mapped into
 * 1900-1999, and local times that do not exist on a DST spring-forward boundary).
 *
 * Args:
 *   value: The `yyyy-mm-ddThh:mm` (seconds optional) input value.
 *
 * Returns:
 *   The ISO-8601 UTC timestamp, or null when the value is blank or not a real instant.
 */
export function localDateTimeToIsoInstant(value: string): string | null {
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
