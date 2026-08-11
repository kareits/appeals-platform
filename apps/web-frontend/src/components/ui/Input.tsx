/**
 * Shared text input primitive.
 *
 * A thin wrapper over the native `<input>` that applies the design-system control styling and
 * forwards every native prop (type, value, onChange, aria-*). It exists so forms compose a
 * consistent control; behavior and accessibility are identical to a bare input.
 */
import type { InputHTMLAttributes } from "react";

/** Props for the shared input (all native input attributes). */
export type InputProps = InputHTMLAttributes<HTMLInputElement>;

/**
 * Render a design-system text input.
 *
 * Args:
 *   props: Native input props, including an optional `className` appended to the control class.
 *
 * Returns:
 *   The styled input element.
 */
export function Input({ className, ...rest }: InputProps): React.JSX.Element {
  const classes = ["input", className ?? ""].filter(Boolean).join(" ");
  return <input className={classes} {...rest} />;
}
