/**
 * Component tests for the appeal-card page.
 *
 * These exercise the real API client, decoders, and TanStack Query against a URL-routed `fetch`
 * stub: the read-only view (first-line users see the card and comments but no command forms), the
 * privileged view (command forms appear per permission), and the not-found state. The
 * registration→decision→close acceptance flow lives in `cardFlow.e2e.test.tsx`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { TicketCardPage } from "./TicketCardPage";
import {
  makeTicketCard,
  renderWithProviders,
  stubFetchByUrl,
  type FakeResponse,
} from "../../test/utils";
import type { Session } from "../../auth/session";
import type { CommentResponse, ReferenceDataResponse, TicketResponse } from "../../api/types";

const CARD_ID = "00000000-0000-0000-0000-0000000000cc";

/** A first-line read-only session (card and comments visible, no command forms). */
const READONLY_SESSION: Session = {
  accessToken: "test-token",
  subject: "00000000-0000-0000-0000-000000000001",
  username: "firstline",
  roles: ["FIRST_LINE_READONLY"],
  permissions: ["ticket:read"],
};

/** A supervisor session holding every card command permission. */
const PRIVILEGED_SESSION: Session = {
  accessToken: "test-token",
  subject: "00000000-0000-0000-0000-0000000000b2",
  username: "supervisor",
  roles: ["SUPERVISOR"],
  permissions: [
    "ticket:read",
    "ticket:update",
    "ticket:classify",
    "ticket:comment",
    "ticket:decide",
    "ticket:close",
    "ticket:legal_hold",
  ],
};

/** Reference data covering every dictionary the card page reads. */
const REFERENCE_DATA: ReferenceDataResponse = {
  entries: [
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

/** A single comment attached to the appeal. */
const COMMENT: CommentResponse = {
  id: "00000000-0000-0000-0000-0000000000c1",
  ticketId: CARD_ID,
  authorId: "00000000-0000-0000-0000-000000000001",
  body: "A prior note",
  createdAt: "2026-08-01T10:00:00Z",
};

/** Build a workspace envelope carrying the given card and comments. */
function workspaceFor(card: TicketResponse, comments: CommentResponse[]): Record<string, unknown> {
  const placeholder = { status: "not_implemented", data: null };
  return {
    ticketId: card.id,
    degraded: false,
    sections: {
      ticket: { status: "ok", data: card },
      comments: { status: "ok", data: comments },
      process: placeholder,
      mail: placeholder,
      documents: placeholder,
    },
  };
}

/** Route the card page's reads (reference + workspace) for a static card. */
function staticRoutes(card: TicketResponse): (url: string) => FakeResponse {
  return (url: string) => {
    if (url.includes("/reference-data")) {
      return { status: 200, json: REFERENCE_DATA };
    }
    if (url.includes("/workspace")) {
      return { status: 200, json: workspaceFor(card, [COMMENT]) };
    }
    throw new Error(`unexpected request: ${url}`);
  };
}

/** Render the card page at its route so `useParams` resolves the appeal id. */
function renderCard(session: Session): void {
  renderWithProviders(
    <Routes>
      <Route path="/tickets/:ticketId" element={<TicketCardPage />} />
    </Routes>,
    { session, routerEntries: [`/tickets/${CARD_ID}`] },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("TicketCardPage", () => {
  it("shows the card and comments but no command forms for a read-only user", async () => {
    stubFetchByUrl(staticRoutes(makeTicketCard()));
    renderCard(READONLY_SESSION);

    // The registration number and localized status label render.
    expect(await screen.findByText(/AP-2026-000123/)).toBeInTheDocument();
    expect(screen.getByText("Новое")).toBeInTheDocument();
    // The existing comment is shown.
    expect(screen.getByText("A prior note")).toBeInTheDocument();

    // No command forms and no add-comment control for a read-only user.
    expect(screen.queryByRole("form", { name: "Записать решение" })).toBeNull();
    expect(screen.queryByRole("form", { name: "Закрыть обращение" })).toBeNull();
    expect(screen.queryByLabelText("Новый комментарий")).toBeNull();
  });

  it("shows the command forms for a privileged user", async () => {
    stubFetchByUrl(staticRoutes(makeTicketCard()));
    renderCard(PRIVILEGED_SESSION);

    expect(await screen.findByText(/AP-2026-000123/)).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Редактировать данные" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Классификация" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Записать решение" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Закрыть обращение" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Юридическая блокировка" })).toBeInTheDocument();
    expect(screen.getByLabelText("Новый комментарий")).toBeInTheDocument();
  });

  it("shows a not-found message when the appeal does not exist", async () => {
    stubFetchByUrl((url) => {
      if (url.includes("/reference-data")) {
        return { status: 200, json: REFERENCE_DATA };
      }
      return { status: 404, json: { title: "Not Found", status: 404 } };
    });
    renderCard(PRIVILEGED_SESSION);

    expect(await screen.findByText("Обращение не найдено.")).toBeInTheDocument();
  });
});
