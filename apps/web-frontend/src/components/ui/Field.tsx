/**
 * Shared labelled form field.
 *
 * Wraps a single form control with its label, an optional required marker, an optional hint, and an
 * inline validation error. The control is passed as the single child; the field wires accessibility
 * automatically by cloning it to set `id`, `aria-invalid` when there is an error, and
 * `aria-describedby` pointing at the error/hint text (WCAG 3.3.1/1.3.1), unless the child already
 * sets those. The label is associated with the control through the shared `id`, so tests and screen
 * readers resolve the control by its visible label as before.
 */
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

/** Props for the labelled field. */
export interface FieldProps {
  /** The control id, shared by the label association and the ARIA wiring. */
  id: string;
  /** The visible, already-localized label text. */
  label: ReactNode;
  /** The single form control (input/select/textarea or a wrapper of one). */
  children: ReactElement<Record<string, unknown>>;
  /** Whether the field is required (renders a required marker after the label). */
  required?: boolean;
  /** An already-localized validation error, or null/undefined when the field is valid. */
  error?: string | null;
  /** An optional already-localized hint shown under the control. */
  hint?: string | null;
}

/**
 * Render a labelled field with accessible error/hint wiring.
 *
 * Args:
 *   props: The control id, label, control child, and optional required/error/hint.
 *
 * Returns:
 *   The field element (a `<label>` wrapping the caption, control, and messages).
 */
export function Field({
  id,
  label,
  children,
  required = false,
  error,
  hint,
}: FieldProps): React.JSX.Element {
  const { t } = useTranslation();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ");

  // Clone the control to wire id and ARIA state without the caller repeating it, while letting an
  // explicit prop on the child win (so a control can opt out of the defaults).
  const childProps = children.props;
  const control = isValidElement(children)
    ? cloneElement(children, {
        id: childProps.id ?? id,
        "aria-invalid": childProps["aria-invalid"] ?? (error ? true : undefined),
        "aria-describedby": childProps["aria-describedby"] ?? (describedBy || undefined),
      })
    : children;

  return (
    <label className="field" htmlFor={id}>
      <span className="field__label">
        {label}
        {required ? (
          <>
            {" "}
            <abbr className="required-mark" title={t("common.required")}>
              *
            </abbr>
          </>
        ) : null}
      </span>
      {control}
      {hint ? (
        <span className="field__hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="field__error" id={errorId}>
          {error}
        </span>
      ) : null}
    </label>
  );
}
