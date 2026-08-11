/**
 * Accessibility (axe) checks for the core EP-1 screens (TASK_01E-5 DoD).
 *
 * Renders the login, appeal list, registration, and appeal-card screens against the real providers
 * and stubbed gateway responses, then runs axe over each to assert there are no WCAG A/AA
 * structural violations (labels, roles, names, ARIA). Contrast is excluded here (jsdom limitation)
 * and guaranteed by the design tokens instead; see `test/axe.ts`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { LoginPage } from "./features/login/LoginPage";
import { TicketListPage } from "./features/tickets/TicketListPage";
import { RegisterTicketPage } from "./features/tickets/RegisterTicketPage";
import { TicketCardPage } from "./features/tickets/TicketCardPage";
import {
  makeTicketCard,
  renderWithProviders,
  stubFetch,
  stubFetchByUrl,
  type FakeResponse,
} from "./test/utils";
import { expectNoAxeViolations } from "./test/axe";
import type { Session } from "./auth/session";
import type { ReferenceDataResponse, TicketResponse } from "./api/types";

const CARD_ID = "00000000-0000-0000-0000-0000000000cc";

/** A supervisor session holding every card permission (so all controls render for the checks). */
const PRIVILEGED_SESSION: Session = {
  accessToken: "test-token",
  subject: "00000000-0000-0000-0000-0000000000b2",
  username: "supervisor",
  roles: ["SUPERVISOR"],
  permissions: [
    "ticket:read",
    "ticket:create",
    "ticket:update",
    "ticket:classify",
    "ticket:comment",
    "ticket:decide",
    "ticket:close",
    "ticket:legal_hold",
  ],
};

/** Reference data covering every dictionary the registration and card screens read. */
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
      dictionaryType: "status",
      code: "NEW",
      displayNameRu: "Новое",
      displayNameKk: null,
      sortOrder: 10,
    },
    {
      dictionaryType: "stage",
      code: "REGISTRATION",
      displayNameRu: "Регистрация",
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
    {
      dictionaryType: "gender",
      code: "MALE",
      displayNameRu: "Мужской",
      displayNameKk: null,
      sortOrder: 10,
    },
  ],
};

/** Build a workspace envelope carrying the given card and no comments. */
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

describe("core screens accessibility (axe)", () => {
  it("login page has no WCAG A/AA violations", async () => {
    const { container } = renderWithProviders(<LoginPage />, { routerEntries: ["/login"] });
    await screen.findByRole("button", { name: "Войти" });
    await expectNoAxeViolations(container);
  });

  it("appeal list page has no WCAG A/AA violations", async () => {
    stubFetch([{ status: 200, json: { items: [], page: { page: 1, pageSize: 20, total: 0 } } }]);
    const { container } = renderWithProviders(<TicketListPage />, {
      session: PRIVILEGED_SESSION,
    });
    await screen.findByText("Обращения не найдены.");
    await expectNoAxeViolations(container);
  });

  it("registration page has no WCAG A/AA violations", async () => {
    stubFetch([{ status: 200, json: REFERENCE_DATA }]);
    const { container } = renderWithProviders(<RegisterTicketPage />, {
      session: PRIVILEGED_SESSION,
    });
    await screen.findByRole("option", { name: "Микрокредит" });
    await expectNoAxeViolations(container);
  });

  it("appeal card page has no WCAG A/AA violations", async () => {
    const routes = (url: string): FakeResponse => {
      if (url.includes("/reference-data")) {
        return { status: 200, json: REFERENCE_DATA };
      }
      if (url.includes("/workspace")) {
        return { status: 200, json: workspaceFor(makeTicketCard()) };
      }
      throw new Error(`unexpected request: ${url}`);
    };
    stubFetchByUrl(routes);
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/tickets/:ticketId" element={<TicketCardPage />} />
      </Routes>,
      { session: PRIVILEGED_SESSION, routerEntries: [`/tickets/${CARD_ID}`] },
    );
    await screen.findByText(/AP-2026-000123/);
    await waitFor(() =>
      expect(screen.getByRole("form", { name: "Записать решение" })).toBeInTheDocument(),
    );
    await expectNoAxeViolations(container);
  });
});
