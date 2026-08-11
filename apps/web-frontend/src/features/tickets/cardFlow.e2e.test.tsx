/**
 * End-to-end acceptance test for the appeal lifecycle: registration -> decision -> close.
 *
 * Drives the whole routed application (login excluded — a session is seeded) against a stateful
 * URL-routed `fetch` stub that mutates a single card as the commands land, mirroring the gateway. It
 * exercises the real API client, decoders, hooks, and TanStack Query end to end: an operator
 * registers an appeal, opens it from the list, records a decision, and closes it, reaching the
 * placeholder terminal state (DoD 01E-4, "registration -> decision -> close").
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../App";
import {
  makeTicketCard,
  renderWithProviders,
  stubFetchByUrl,
  type FakeResponse,
} from "../../test/utils";
import type { Session } from "../../auth/session";
import type { ReferenceDataResponse, TicketResponse } from "../../api/types";

const REG_NUMBER = "AP-2026-000123";

/** A session holding registration and all card-command permissions. */
const FULL_SESSION: Session = {
  accessToken: "test-token",
  subject: "00000000-0000-0000-0000-0000000000b2",
  username: "supervisor",
  roles: ["SUPERVISOR"],
  permissions: ["ticket:read", "ticket:create", "ticket:decide", "ticket:close"],
};

/** Reference data covering the registration and card dictionaries the flow uses. */
const REFERENCE_DATA: ReferenceDataResponse = {
  entries: [
    {
      dictionaryType: "channel",
      code: "EMAIL",
      displayNameRu: "Эл. почта",
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
      sortOrder: 10,
    },
    {
      dictionaryType: "decision",
      code: "SATISFIED",
      displayNameRu: "Удовлетворено",
      displayNameKk: null,
      sortOrder: 10,
    },
    {
      dictionaryType: "closure_reason",
      code: "RESOLVED",
      displayNameRu: "Решено",
      displayNameKk: null,
      sortOrder: 10,
    },
  ],
};

/** Build the search-result summary for the current card. */
function summaryFor(card: TicketResponse): Record<string, unknown> {
  return {
    id: card.id,
    registrationNumber: card.registrationNumber,
    subject: card.subject,
    currentStatusCode: card.currentStatusCode,
    currentStageCode: card.currentStageCode,
    productCode: card.productCode,
    classifierCode: card.classifierCode,
    priorityCode: card.priorityCode,
    contractNumber: card.contractNumber,
    currentAssigneeId: card.currentAssigneeId,
    currentTeamId: card.currentTeamId,
    receivedAt: card.receivedAt,
    registeredAt: card.registeredAt,
  };
}

/** Build the workspace envelope for the current card (no comments). */
function workspaceFor(card: TicketResponse): Record<string, unknown> {
  const placeholder = { status: "not_implemented", data: null };
  return {
    ticketId: card.id,
    degraded: false,
    sections: {
      ticket: { status: "ok", data: card },
      comments: { status: "ok", data: [] },
      process: placeholder,
      mail: placeholder,
      documents: placeholder,
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("appeal lifecycle (registration -> decision -> close)", () => {
  it("registers, decides, and closes an appeal through the UI", async () => {
    // The gateway state: one appeal card mutated as the commands land.
    let card = makeTicketCard();
    const routes = (url: string, init: RequestInit): FakeResponse => {
      const method = (init.method ?? "GET").toUpperCase();
      const path = url.split("?")[0] ?? url;
      if (url.includes("/reference-data")) {
        return { status: 200, json: REFERENCE_DATA };
      }
      if (url.includes("/workspace")) {
        return { status: 200, json: workspaceFor(card) };
      }
      if (url.includes("/decision")) {
        card = {
          ...card,
          decisionCode: "SATISFIED",
          decisionSummary: null,
          decisionText: "Решение по обращению принято",
          decisionAt: "2026-08-05T09:00:00Z",
          version: card.version + 1,
        };
        return { status: 200, json: card };
      }
      if (url.includes("/close")) {
        card = {
          ...card,
          closureReasonCode: "RESOLVED",
          closedAt: "2026-08-06T09:00:00Z",
          noResponseReason: "Ответ не требовался",
          currentStatusCode: "COMPLETED",
          currentStageCode: "CLOSED",
          version: card.version + 1,
        };
        return { status: 200, json: card };
      }
      if (method === "POST" && path.endsWith("/tickets")) {
        return { status: 201, json: card };
      }
      if (method === "GET" && path.endsWith("/tickets")) {
        return {
          status: 200,
          json: { items: [summaryFor(card)], page: { page: 1, pageSize: 20, total: 1 } },
        };
      }
      throw new Error(`unexpected request: ${method} ${url}`);
    };
    stubFetchByUrl(routes);
    const user = userEvent.setup();
    renderWithProviders(<App />, { session: FULL_SESSION, routerEntries: ["/tickets/new"] });

    // 1. Register the appeal.
    await screen.findByRole("option", { name: "Микрокредит" });
    fireEvent.change(screen.getByLabelText(/Дата поступления/), {
      target: { value: "2026-08-01T09:00" },
    });
    await user.type(screen.getByLabelText(/^Тема/), "Restructuring request");
    await user.type(screen.getByLabelText(/Текст обращения/), "Full appeal text");
    await user.selectOptions(screen.getByLabelText(/Канал поступления/), "EMAIL");
    await user.selectOptions(screen.getByLabelText(/Продукт/), "MICROLOAN");
    await user.selectOptions(screen.getByLabelText(/Классификатор/), "RESTRUCTURING");
    await user.selectOptions(screen.getByLabelText(/Приоритет/), "NORMAL");
    await user.click(screen.getByRole("button", { name: "Зарегистрировать" }));
    expect(await screen.findByText(new RegExp(REG_NUMBER))).toBeInTheDocument();

    // 2. Go to the list and open the appeal card.
    await user.click(screen.getByRole("link", { name: "К списку обращений" }));
    const cardLink = await screen.findByRole("link", { name: REG_NUMBER });
    await user.click(cardLink);

    // The card page renders (its title carries the registration number).
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: new RegExp(REG_NUMBER) })).toBeInTheDocument(),
    );

    // 3. Record the decision.
    const decisionForm = screen.getByRole("form", { name: "Записать решение" });
    await user.selectOptions(within(decisionForm).getByLabelText(/Решение/), "SATISFIED");
    await user.type(
      within(decisionForm).getByLabelText(/Текст решения/),
      "Решение по обращению принято",
    );
    await user.click(within(decisionForm).getByRole("button", { name: "Сохранить решение" }));
    // After the refetch the card detail block shows the recorded decision text (scoped to the
    // read-only details section so it is not confused with the decision form's prefilled input).
    await waitFor(() =>
      expect(
        within(screen.getByLabelText("Данные обращения")).getByText("Решение по обращению принято"),
      ).toBeInTheDocument(),
    );

    // 4. Close the appeal.
    const closeForm = screen.getByRole("form", { name: "Закрыть обращение" });
    await user.selectOptions(within(closeForm).getByLabelText(/Причина закрытия/), "RESOLVED");
    await user.type(
      within(closeForm).getByLabelText(/Причина отсутствия ответа/),
      "Ответ не требовался",
    );
    await user.click(within(closeForm).getByRole("button", { name: "Закрыть обращение" }));
    // The appeal reaches its terminal (closed) state; the close form reports it is already closed.
    expect(await screen.findByText("Обращение уже закрыто.")).toBeInTheDocument();
  });
});
