/**
 * Regression tests for cross-user query-cache isolation (CR-WEB-HIGH-001).
 *
 * A single tab that logs in as A, logs out, then logs in as B must never render A's ticket data to
 * B, and an A request that completes after logout must not populate the shared cache. These tests
 * drive real login/logout through the auth context against a URL-aware fetch mock and inspect both
 * the DOM and the QueryClient cache.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../auth/AuthContext";
import { useAuth } from "../../auth/context";
import { TicketListPage } from "./TicketListPage";
import { makeResponse, newTestQueryClient } from "../../test/utils";
import "../../i18n";

/** Distinct valid UUIDs per test user (subject and ticket id must be UUID-formatted). */
const SUBJECTS: Record<string, string> = {
  alice: "11111111-1111-1111-1111-111111111111",
  bob: "22222222-2222-2222-2222-222222222222",
};
const TICKET_IDS: Record<string, string> = {
  alice: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  bob: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
};

function tokenFor(user: string): Record<string, unknown> {
  return {
    accessToken: `token-${user}`,
    tokenType: "Bearer",
    expiresIn: 3600,
    subject: SUBJECTS[user],
    username: user,
    roles: ["EMPLOYEE"],
    permissions: ["ticket:read"],
    teams: [],
  };
}

function pageFor(user: string): Record<string, unknown> {
  const tag = user.toUpperCase();
  return {
    items: [
      {
        id: TICKET_IDS[user],
        registrationNumber: `AP-${tag}`,
        subject: `${tag} appeal`,
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
      },
    ],
    page: { page: 1, pageSize: 20, total: 1 },
  };
}

/** Test harness exposing login/logout controls around the appeal list. */
function Harness(): React.JSX.Element {
  const { login, logout, isAuthenticated, session } = useAuth();
  return (
    <div>
      <button onClick={() => void login({ username: "alice", password: "x" })}>login-alice</button>
      <button onClick={() => void login({ username: "bob", password: "x" })}>login-bob</button>
      <button onClick={() => logout()}>logout</button>
      <span data-testid="who">{session?.username ?? "none"}</span>
      {isAuthenticated ? <TicketListPage /> : <span>logged-out</span>}
    </div>
  );
}

function renderHarness(queryClient: QueryClient): void {
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter>
          <Harness />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function cacheMentions(queryClient: QueryClient, needle: string): boolean {
  return queryClient
    .getQueryCache()
    .getAll()
    .some((query) => JSON.stringify(query.state.data ?? "").includes(needle));
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("cross-user cache isolation", () => {
  it("never shows the previous user's tickets after logout and re-login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/auth/login")) {
          const user = JSON.parse(init!.body as string).username as string;
          return makeResponse({ json: tokenFor(user) });
        }
        const auth = (init!.headers as Record<string, string>)["Authorization"] ?? "";
        return makeResponse({ json: pageFor(auth.includes("token-alice") ? "alice" : "bob") });
      }),
    );
    const queryClient = newTestQueryClient();
    const user = userEvent.setup();
    renderHarness(queryClient);

    await user.click(screen.getByRole("button", { name: "login-alice" }));
    expect(await screen.findByText("AP-ALICE")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "logout" }));
    await screen.findByText("logged-out");
    expect(screen.queryByText("AP-ALICE")).not.toBeInTheDocument();
    expect(cacheMentions(queryClient, "AP-ALICE")).toBe(false);

    await user.click(screen.getByRole("button", { name: "login-bob" }));
    expect(await screen.findByText("AP-BOB")).toBeInTheDocument();
    expect(screen.queryByText("AP-ALICE")).not.toBeInTheDocument();
    expect(cacheMentions(queryClient, "AP-ALICE")).toBe(false);
  });

  it("does not populate the cache from a request that completes after logout", async () => {
    let deferred: { resolve: () => void; signal: AbortSignal | null } | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/auth/login")) {
          const user = JSON.parse(init!.body as string).username as string;
          return Promise.resolve(makeResponse({ json: tokenFor(user) }));
        }
        return new Promise<Response>((resolve, reject) => {
          const signal = init?.signal ?? null;
          deferred = {
            resolve: () => resolve(makeResponse({ json: pageFor("alice") })),
            signal,
          };
          signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        });
      }),
    );
    const queryClient = newTestQueryClient();
    const user = userEvent.setup();
    renderHarness(queryClient);

    await user.click(screen.getByRole("button", { name: "login-alice" }));
    await waitFor(() => expect(deferred).not.toBeNull());
    expect(screen.getByTestId("who")).toHaveTextContent("alice");

    // Log out while alice's ticket request is still in flight.
    await user.click(screen.getByRole("button", { name: "logout" }));
    await screen.findByText("logged-out");
    await waitFor(() => expect(deferred!.signal!.aborted).toBe(true));

    // A late completion of the aborted request must not surface or populate the cache.
    deferred!.resolve();
    await Promise.resolve();
    expect(screen.queryByText("AP-ALICE")).not.toBeInTheDocument();
    expect(cacheMentions(queryClient, "AP-ALICE")).toBe(false);
  });
});
