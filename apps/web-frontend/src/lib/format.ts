/**
 * Small formatting helpers shared by presentational components.
 */

/**
 * Format an ISO-8601 timestamp for display in the given locale.
 *
 * Falls back to the raw value when it cannot be parsed, so malformed data is shown rather than
 * hidden.
 *
 * Args:
 *   iso: The ISO-8601 timestamp.
 *   locale: The active UI locale (for example, "ru" or "kk").
 *
 * Returns:
 *   A locale-formatted date-time string, or the raw input when unparseable.
 */
export function formatDateTime(iso: string, locale: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}
