/**
 * Badge tone selection for appeal status and priority codes.
 *
 * Kept separate from the Badge component so the tone mapping can be reused (list and card) and unit
 * tested without importing a component module (which also keeps the component file export-clean for
 * React Fast Refresh).
 */

/** The semantic tones a badge can take. */
export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

/** Appeal status codes grouped by the tone that best conveys their state. */
const STATUS_TONE: Record<string, BadgeTone> = {
  NEW: "info",
  REGISTRATION: "neutral",
  IN_PROGRESS: "info",
  IN_REVIEW: "info",
  ON_HOLD: "warning",
  WAITING: "warning",
  COMPLETED: "success",
  RESOLVED: "success",
  CLOSED: "neutral",
  REJECTED: "danger",
};

/** Appeal priority codes grouped by escalating tone. */
const PRIORITY_TONE: Record<string, BadgeTone> = {
  LOW: "neutral",
  NORMAL: "info",
  HIGH: "warning",
  URGENT: "danger",
  CRITICAL: "danger",
};

/**
 * Resolve the badge tone for an appeal status or priority code.
 *
 * Args:
 *   kind: Which dictionary the code belongs to ("status" or "priority").
 *   code: The raw code, or null/undefined when unknown.
 *
 * Returns:
 *   The mapped tone, or "neutral" for an unknown or missing code.
 */
export function badgeTone(kind: "status" | "priority", code: string | null | undefined): BadgeTone {
  if (!code) {
    return "neutral";
  }
  const table = kind === "status" ? STATUS_TONE : PRIORITY_TONE;
  return table[code] ?? "neutral";
}
