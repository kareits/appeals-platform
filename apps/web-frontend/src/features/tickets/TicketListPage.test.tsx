/**
 * Component tests for the appeal list and search page.
 *
 * These exercise the real API client and TanStack Query against a stubbed `fetch`, covering the
 * result table, filter submission (including page reset and query mapping), the empty state, and
 * the forbidden state.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TicketListPage } from "./TicketListPage";
import { renderWithProviders, stubDeferredFetch, stubFetch, TEST_SESSION } from "../../test/utils";
import type { PaginatedTickets, TicketSummary } from "../../api/types";

function summary(overrides: Partial<TicketSummary> = {}): TicketSummary {
  return {
    id: "00000000-0000-0000-0000-0000000000aa",
    registrationNumber: "AP-2026-000001",
    subject: "Late fee dispute",
    currentStatusCode: "REGISTERED",
    currentStageCode: "INTAKE",
    productCode: "LOAN",
    classifierCode: "COMPLAINT",
    priorityCode: "NORMAL",
    contractNumber: null,
    currentAssigneeId: null,
    currentTeamId: null,
    receivedAt: "2026-07-20T08:00:00Z",
    registeredAt: "2026-07-20T09:00:00Z",
    ...overrides,
  };
}

function page(items: TicketSummary[], total = items.length): PaginatedTickets {
  return { items, page: { page: 1, pageSize: 20, total } };
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("TicketListPage", () => {
  it("renders the appeals returned by the gateway", async () => {
    stubFetch([{ status: 200, json: page([summary()]) }]);
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    expect(await screen.findByText("AP-2026-000001")).toBeInTheDocument();
    expect(screen.getByText("Late fee dispute")).toBeInTheDocument();
  });

  it("forwards entered filters as query parameters and resets to page 1", async () => {
    const fetchMock = stubFetch([
      { status: 200, json: page([summary()]) },
      { status: 200, json: page([summary({ registrationNumber: "AP-2026-000777" })]) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    await screen.findByText("AP-2026-000001");

    await user.type(screen.getByLabelText("Регистрационный номер"), "AP-2026-000777");
    await user.click(screen.getByRole("button", { name: "Найти" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    const secondUrl = fetchMock.mock.calls[1]![0] as string;
    expect(secondUrl).toContain("registrationNumber=AP-2026-000777");
    expect(secondUrl).toContain("page=1");
  });

  it("shows the empty state when no appeals match", async () => {
    stubFetch([{ status: 200, json: page([], 0) }]);
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    expect(await screen.findByText("Обращения не найдены.")).toBeInTheDocument();
  });

  it("shows a permission message on 403", async () => {
    stubFetch([{ status: 403, json: { title: "Forbidden", status: 403 } }]);
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Недостаточно прав для просмотра обращений.",
    );
  });

  it("paginates to the next page when more results exist", async () => {
    const fetchMock = stubFetch([
      { status: 200, json: page([summary()], 40) },
      { status: 200, json: page([summary({ registrationNumber: "AP-2026-000021" })], 40) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    await screen.findByText("AP-2026-000001");
    await user.click(screen.getByRole("button", { name: "Вперёд" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    const table = screen.getByRole("table");
    expect(within(table).getByText("AP-2026-000021")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]![0] as string).toContain("page=2");
  });

  it("shows a bounded Retry-After hint and a manual retry on 429", async () => {
    const fetchMock = stubFetch([
      { status: 429, json: { title: "Too Many", status: 429 }, retryAfter: "7" },
      { status: 200, json: page([summary()]) },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Слишком много запросов. Повторите через 7 с.",
    );

    // The manual retry re-issues the search.
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("AP-2026-000001")).toBeInTheDocument();
  });

  it.each([
    [502, "Сервис временно недоступен (ошибка шлюза)."],
    [503, "Сервис временно недоступен. Повторите попытку позже."],
    [504, "Сервис не ответил вовремя (тайм-аут шлюза)."],
  ])("shows a distinct message for gateway status %s", async (status, message) => {
    stubFetch([{ status, json: { title: "Gateway", status } }]);
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("shows a safe message and the correlation id on an unexpected response", async () => {
    stubFetch([{ status: 200, json: { items: {}, page: {} }, correlationId: "cid-xyz" }]);
    renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Получен некорректный ответ сервера.");
    expect(alert).toHaveTextContent("cid-xyz");
  });

  it("aborts the in-flight search when the page unmounts", async () => {
    const calls = stubDeferredFetch();
    const { unmount } = renderWithProviders(<TicketListPage />, { session: TEST_SESSION });

    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0]!.signal).not.toBeNull();
    expect(calls[0]!.signal!.aborted).toBe(false);

    unmount();
    await waitFor(() => expect(calls[0]!.signal!.aborted).toBe(true));
  });
});
