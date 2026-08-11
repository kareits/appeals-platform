/**
 * Shared alert/feedback banner.
 *
 * Presents a bounded feedback message (error, success, info, or warning) with the design-system
 * styling and the correct ARIA live semantics: errors are assertive alerts (`role="alert"`), while
 * non-error tones are polite status messages (`role="status"`), matching the roles the EP-1 screens
 * already relied on. The component renders content passed as children; it never formats raw server
 * text itself, so callers stay responsible for using safe, localized copy.
 */
import type { ReactNode } from "react";

/** The feedback tones an alert can convey. */
export type AlertTone = "error" | "success" | "info" | "warning";

/** Props for the alert banner. */
export interface AlertProps {
  /** The feedback tone (defaults to "info"). */
  tone?: AlertTone;
  /** The alert content (already localized). */
  children: ReactNode;
  /**
   * Explicit ARIA role override. Defaults to "alert" for the error tone and "status" otherwise; a
   * caller can force either when the live-region urgency differs from the tone.
   */
  role?: "alert" | "status";
  /** Extra class names appended to the tone class. */
  className?: string;
}

/** Maps a tone to its design-system modifier class. */
const TONE_CLASS: Record<AlertTone, string> = {
  error: "alert--error",
  success: "alert--success",
  info: "alert--info",
  warning: "alert--warning",
};

/**
 * Render a feedback banner.
 *
 * Args:
 *   props: The tone, content, optional role override, and extra class names.
 *
 * Returns:
 *   The alert element with the appropriate role for assistive technology.
 */
export function Alert({ tone = "info", children, role, className }: AlertProps): React.JSX.Element {
  const resolvedRole = role ?? (tone === "error" ? "alert" : "status");
  const classes = ["alert", TONE_CLASS[tone], className ?? ""].filter(Boolean).join(" ");
  return (
    <div className={classes} role={resolvedRole}>
      {children}
    </div>
  );
}
