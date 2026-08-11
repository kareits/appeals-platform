/**
 * Shared status/priority badge.
 *
 * Renders a small pill conveying a semantic tone (neutral/info/success/warning/danger). The badge is
 * presentational: it colors a value (for example an appeal status or priority) but always shows the
 * caller-provided text, so the visible label is unchanged from the raw value the screens rendered
 * before. Tone selection for appeal status and priority codes lives in `badgeTone` (a separate
 * module) so the mapping is reused across the list and the card.
 */
import type { ReactNode } from "react";
import type { BadgeTone } from "./badgeTone";

/** Props for the badge. */
export interface BadgeProps {
  /** The semantic tone (defaults to "neutral"). */
  tone?: BadgeTone;
  /** The badge content (already localized or a raw code). */
  children: ReactNode;
}

/** Maps a tone to its design-system modifier class ("neutral" is the base class). */
const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: "",
  info: "badge--info",
  success: "badge--success",
  warning: "badge--warning",
  danger: "badge--danger",
};

/**
 * Render a badge pill.
 *
 * Args:
 *   props: The tone and content.
 *
 * Returns:
 *   The badge element.
 */
export function Badge({ tone = "neutral", children }: BadgeProps): React.JSX.Element {
  const classes = ["badge", TONE_CLASS[tone]].filter(Boolean).join(" ");
  return <span className={classes}>{children}</span>;
}
