/**
 * Barrel for the shared UI primitives (design system, TASK_01E-5 / ADR-0011).
 *
 * Re-exports the design-system components so screens import them from a single path. These
 * primitives are presentation-only wrappers over native elements plus the modal dialog; later
 * frontend screens (02E-*, 05B/05C) reuse the same set for a consistent look.
 */
export { Alert, type AlertProps, type AlertTone } from "./Alert";
export { Badge, type BadgeProps } from "./Badge";
export { badgeTone, type BadgeTone } from "./badgeTone";
export { Button, type ButtonProps, type ButtonVariant } from "./Button";
export { Dialog, type DialogProps } from "./Dialog";
export { Field, type FieldProps } from "./Field";
export { Input, type InputProps } from "./Input";
export { Select, type SelectProps } from "./Select";
export { Textarea, type TextareaProps } from "./Textarea";
