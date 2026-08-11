/**
 * Shared button primitive.
 *
 * A thin wrapper over the native `<button>` that applies the design-system button classes for a
 * consistent look across screens (variant and optional block width). It forwards all native button
 * props (including `type`, `disabled`, `onClick`, and `aria-*`), so behavior and accessibility are
 * unchanged from a bare button; only presentation is standardized.
 */
import type { ButtonHTMLAttributes } from "react";

/** The visual variants a button can take. */
export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

/** Props for the shared button. */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** The visual variant (defaults to "secondary"). */
  variant?: ButtonVariant;
  /** When true, the button stretches to the full width of its container. */
  block?: boolean;
}

/** Maps a variant to its design-system modifier class. */
const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "btn--primary",
  secondary: "",
  danger: "btn--danger",
  ghost: "btn--ghost",
};

/**
 * Render a design-system button.
 *
 * Args:
 *   props: Native button props plus the optional `variant`, `block`, and `className`. The button
 *     `type` defaults to "button" so a button in a form does not submit unless it opts in.
 *
 * Returns:
 *   The styled button element.
 */
export function Button({
  variant = "secondary",
  block = false,
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps): React.JSX.Element {
  const classes = ["btn", VARIANT_CLASS[variant], block ? "btn--block" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  );
}
