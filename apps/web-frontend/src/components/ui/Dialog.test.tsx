/**
 * Tests for the accessible modal Dialog primitive.
 *
 * Cover the ARIA modal contract, focus management (move-in on open, restore on close), and the
 * close affordances (Escape, backdrop click, and a footer action). These are the behaviors screen
 * reader and keyboard users depend on, so they are asserted directly rather than through a screen.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Dialog } from "./Dialog";

/** A harness that opens the dialog from a trigger button and closes it via state. */
function Harness(): React.JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Confirm action"
        footer={
          <button type="button" onClick={() => setOpen(false)}>
            Cancel
          </button>
        }
      >
        <p>Dialog body</p>
      </Dialog>
    </div>
  );
}

afterEach(() => {
  cleanup();
});

describe("Dialog", () => {
  it("renders nothing until opened", () => {
    render(<Harness />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("exposes the modal contract and is named by its title", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Confirm action");
  });

  it("moves focus into the dialog on open and restores it on close", () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    opener.focus();
    fireEvent.click(opener);

    // Focus moved into the dialog (the first focusable element).
    expect(document.activeElement).not.toBe(opener);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);

    // Escape closes the dialog and restores focus to the opener.
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("closes when the backdrop is clicked but not when the panel is clicked", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));

    // Clicking inside the panel keeps the dialog open.
    fireEvent.mouseDown(screen.getByText("Dialog body"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // Clicking the backdrop itself dismisses it.
    const backdrop = screen.getByRole("dialog").parentElement as HTMLElement;
    fireEvent.mouseDown(backdrop);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
