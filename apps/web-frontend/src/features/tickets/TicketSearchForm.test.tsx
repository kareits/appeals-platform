/**
 * Component tests for the appeal search form.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../../i18n";
import { TicketSearchForm } from "./TicketSearchForm";
import { EMPTY_FORM_VALUES } from "./searchValues";

describe("TicketSearchForm", () => {
  it("renders the localized filter fields", () => {
    render(<TicketSearchForm onApply={vi.fn()} />);
    expect(screen.getByLabelText("Регистрационный номер")).toBeInTheDocument();
    expect(screen.getByLabelText("ФИО заявителя")).toBeInTheDocument();
    expect(screen.getByLabelText("Поступило с")).toBeInTheDocument();
  });

  it("applies the entered values on submit", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<TicketSearchForm onApply={onApply} />);

    await user.type(screen.getByLabelText("Регистрационный номер"), "AP-2026-000123");
    await user.type(screen.getByLabelText("Статус"), "REGISTERED");
    await user.click(screen.getByRole("button", { name: "Найти" }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0]![0]).toMatchObject({
      registrationNumber: "AP-2026-000123",
      statusCode: "REGISTERED",
    });
  });

  it("clears the fields and applies empty values on reset", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<TicketSearchForm onApply={onApply} />);

    await user.type(screen.getByLabelText("Регистрационный номер"), "AP-2026-000123");
    await user.click(screen.getByRole("button", { name: "Сбросить" }));

    expect(onApply).toHaveBeenLastCalledWith(EMPTY_FORM_VALUES);
    expect(screen.getByLabelText<HTMLInputElement>("Регистрационный номер").value).toBe("");
  });
});
