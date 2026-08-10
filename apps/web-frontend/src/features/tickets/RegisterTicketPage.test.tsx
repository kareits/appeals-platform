/**
 * Component tests for the manual appeal-registration page.
 *
 * These exercise the real API client, decoders, and TanStack Query against a stubbed `fetch`:
 * reference-data-driven selects, client-side required-field validation, a successful registration
 * (asserting the forwarded body and idempotency key), and the permission guard.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RegisterTicketPage } from "./RegisterTicketPage";
import { renderWithProviders, stubFetch } from "../../test/utils";
import type { Session } from "../../auth/session";
import type { CreateTicketRequest, ReferenceDataResponse, TicketResponse } from "../../api/types";

/** A session that may register appeals (ticket:create). */
const CREATE_SESSION: Session = {
  accessToken: "test-token",
  subject: "00000000-0000-0000-0000-000000000001",
  username: "employee",
  roles: ["EMPLOYEE"],
  permissions: ["ticket:read", "ticket:create"],
};

/** A read-only session that may not register appeals. */
const READONLY_SESSION: Session = {
  ...CREATE_SESSION,
  username: "firstline",
  roles: ["FIRST_LINE_READONLY"],
  permissions: ["ticket:read"],
};

/** Canned reference-data covering the dictionaries the form needs. */
const REFERENCE_DATA: ReferenceDataResponse = {
  entries: [
    {
      dictionaryType: "channel",
      code: "EMAIL",
      displayNameRu: "Электронная почта",
      displayNameKk: null,
      sortOrder: 10,
    },
    {
      dictionaryType: "product",
      code: "MICROLOAN",
      displayNameRu: "Микрокредит",
      displayNameKk: null,
      sortOrder: 10,
    },
    {
      dictionaryType: "classifier",
      code: "RESTRUCTURING",
      displayNameRu: "Реструктуризация",
      displayNameKk: null,
      sortOrder: 10,
    },
    {
      dictionaryType: "priority",
      code: "NORMAL",
      displayNameRu: "Обычный",
      displayNameKk: null,
      sortOrder: 20,
    },
    {
      dictionaryType: "gender",
      code: "MALE",
      displayNameRu: "Мужской",
      displayNameKk: null,
      sortOrder: 10,
    },
  ],
};

/** A canned created-appeal card returned by the gateway. */
const CREATED: TicketResponse = {
  id: "00000000-0000-0000-0000-0000000000cc",
  registrationNumber: "AP-2026-000123",
  subject: "Restructuring request",
  productCode: "MICROLOAN",
  classifierCode: "RESTRUCTURING",
  priorityCode: "NORMAL",
  currentStatusCode: "NEW",
  currentStageCode: "REGISTRATION",
  isConfidential: false,
  version: 1,
};

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

/** Fill the required main-section fields with valid values. */
async function fillRequired(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  fireEvent.change(screen.getByLabelText(/Дата поступления/), {
    target: { value: "2026-08-01T09:00" },
  });
  await user.type(screen.getByLabelText(/Тема/), "Restructuring request");
  await user.type(screen.getByLabelText(/Текст обращения/), "Full appeal text");
  await user.selectOptions(screen.getByLabelText(/Канал поступления/), "EMAIL");
  await user.selectOptions(screen.getByLabelText(/Продукт/), "MICROLOAN");
  await user.selectOptions(screen.getByLabelText(/Классификатор/), "RESTRUCTURING");
  await user.selectOptions(screen.getByLabelText(/Приоритет/), "NORMAL");
}

describe("RegisterTicketPage", () => {
  it("populates selects from reference data and registers an appeal", async () => {
    const fetchMock = stubFetch([
      { status: 200, json: REFERENCE_DATA },
      { status: 201, json: CREATED },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<RegisterTicketPage />, { session: CREATE_SESSION });

    // The product select is populated from reference data.
    await screen.findByRole("option", { name: "Микрокредит" });

    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Зарегистрировать" }));

    // The assigned registration number is shown on success.
    expect(await screen.findByText(/AP-2026-000123/)).toBeInTheDocument();

    // The create call forwarded the body and an idempotency key.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(String(url)).toContain("/api/v1/tickets");
    expect(init!.method).toBe("POST");
    const headers = init!.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBeTruthy();
    const body = JSON.parse(init!.body as string) as CreateTicketRequest;
    expect(body.subject).toBe("Restructuring request");
    expect(body.productCode).toBe("MICROLOAN");
    expect(body.applicant.applicantType).toBe("CONSUMER");
    // Blank demographic fields are sent as null (conditionals nullable).
    expect(body.applicant.fullName).toBeNull();
    expect(body.representative).toBeNull();
  });

  it("shows required-field errors and does not call the gateway when fields are empty", async () => {
    const fetchMock = stubFetch([{ status: 200, json: REFERENCE_DATA }]);
    const user = userEvent.setup();
    renderWithProviders(<RegisterTicketPage />, { session: CREATE_SESSION });

    await screen.findByRole("option", { name: "Микрокредит" });
    await user.click(screen.getByRole("button", { name: "Зарегистрировать" }));

    // A required-field message is shown and no create request is made (only reference data was
    // fetched).
    expect(await screen.findAllByText("Обязательное поле.")).not.toHaveLength(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("relays a gateway validation error to the user", async () => {
    stubFetch([
      { status: 200, json: REFERENCE_DATA },
      { status: 422, json: { title: "Invalid ticket", status: 422 }, correlationId: "cid-9" },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<RegisterTicketPage />, { session: CREATE_SESSION });

    await screen.findByRole("option", { name: "Микрокредит" });
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Зарегистрировать" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Не удалось обработать данные: ошибка валидации.");
    expect(alert).toHaveTextContent("cid-9");
  });

  it("denies access without the create permission", async () => {
    stubFetch([{ status: 200, json: REFERENCE_DATA }]);
    renderWithProviders(<RegisterTicketPage />, { session: READONLY_SESSION });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Недостаточно прав для регистрации обращений.",
    );
    expect(screen.queryByRole("button", { name: "Зарегистрировать" })).not.toBeInTheDocument();
  });
});
