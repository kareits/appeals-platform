/**
 * Shared accessible modal dialog.
 *
 * Renders a modal dialog into a portal on `document.body` with the ARIA modal contract
 * (`role="dialog"`, `aria-modal="true"`, `aria-labelledby` bound to the title). It manages focus for
 * keyboard and screen-reader users: on open it moves focus into the dialog and remembers the
 * previously focused element; while open it traps Tab within the dialog and closes on Escape or a
 * backdrop click; on close it restores focus to the element that opened it (WCAG 2.1.2/2.4.3). When
 * closed it renders nothing. Presentation and interaction only — callers own the action handlers.
 */
import { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

/** Props for the modal dialog. */
export interface DialogProps {
  /** Whether the dialog is open (renders nothing when false). */
  open: boolean;
  /** Called when the user requests to close (Escape, backdrop click, or a close action). */
  onClose: () => void;
  /** The dialog title, used as its accessible name. */
  title: string;
  /** The dialog body content. */
  children: ReactNode;
  /** Optional footer actions (buttons); rendered in the actions row when provided. */
  footer?: ReactNode;
}

/** CSS selector matching the tabbable elements used for the focus trap. */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Render an accessible modal dialog.
 *
 * Args:
 *   props: The open flag, close handler, title, body children, and optional footer actions.
 *
 * Returns:
 *   The dialog portal when open, otherwise null.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
}: DialogProps): React.JSX.Element | null {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  const focusables = useCallback((): HTMLElement[] => {
    const root = dialogRef.current;
    if (!root) {
      return [];
    }
    return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
  }, []);

  // Remember the opener and restore focus to it when the dialog closes or unmounts.
  useEffect(() => {
    if (!open) {
      return;
    }
    const opener = document.activeElement as HTMLElement | null;
    // Move focus into the dialog once it is mounted (the first focusable element, or the panel).
    const first = focusables()[0] ?? dialogRef.current;
    first?.focus();
    return () => {
      opener?.focus();
    };
  }, [open, focusables]);

  // Escape to close and Tab to cycle focus within the dialog.
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0]!;
      const last = items[items.length - 1]!;
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose, focusables]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div
      className="dialog__backdrop"
      onMouseDown={(event) => {
        // Only a click on the backdrop itself (not a child) dismisses the dialog.
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
      >
        <h2 className="dialog__title" id={titleId}>
          {title}
        </h2>
        <div className="dialog__body">{children}</div>
        {footer ? <div className="dialog__actions">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
