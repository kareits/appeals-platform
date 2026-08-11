/**
 * Shared select primitive.
 *
 * A thin wrapper over the native `<select>` applying the design-system control styling and
 * forwarding every native prop (value, onChange, aria-*). Options are passed as children so callers
 * keep full control over the option list; presentation only, behavior matches a bare select.
 */
import type { SelectHTMLAttributes } from "react";

/** Props for the shared select (all native select attributes). */
export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

/**
 * Render a design-system select.
 *
 * Args:
 *   props: Native select props (including the option children) and an optional `className` appended
 *     to the control class.
 *
 * Returns:
 *   The styled select element.
 */
export function Select({ className, children, ...rest }: SelectProps): React.JSX.Element {
  const classes = ["select", className ?? ""].filter(Boolean).join(" ");
  return (
    <select className={classes} {...rest}>
      {children}
    </select>
  );
}
