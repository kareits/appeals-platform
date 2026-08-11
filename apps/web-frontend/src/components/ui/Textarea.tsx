/**
 * Shared multi-line text input primitive.
 *
 * A thin wrapper over the native `<textarea>` applying the design-system control styling and
 * forwarding every native prop. Presentation only; behavior and accessibility match a bare textarea.
 */
import type { TextareaHTMLAttributes } from "react";

/** Props for the shared textarea (all native textarea attributes). */
export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

/**
 * Render a design-system textarea.
 *
 * Args:
 *   props: Native textarea props, including an optional `className` appended to the control class.
 *
 * Returns:
 *   The styled textarea element.
 */
export function Textarea({ className, ...rest }: TextareaProps): React.JSX.Element {
  const classes = ["textarea", className ?? ""].filter(Boolean).join(" ");
  return <textarea className={classes} {...rest} />;
}
