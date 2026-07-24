/**
 * Tests for the authentication route guard.
 */
import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../auth/AuthContext";
import { RequireAuth } from "./RequireAuth";
import { newTestQueryClient, TEST_SESSION } from "../test/utils";

function renderGuarded(): void {
  render(
    <QueryClientProvider client={newTestQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/tickets"]}>
          <Routes>
            <Route path="/login" element={<div>login-screen</div>} />
            <Route
              path="/tickets"
              element={
                <RequireAuth>
                  <div>protected-content</div>
                </RequireAuth>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  sessionStorage.clear();
});

describe("RequireAuth", () => {
  it("redirects to login when unauthenticated", () => {
    renderGuarded();
    expect(screen.getByText("login-screen")).toBeInTheDocument();
    expect(screen.queryByText("protected-content")).not.toBeInTheDocument();
  });

  it("renders the protected content when authenticated", () => {
    sessionStorage.setItem("mfo.auth.session", JSON.stringify(TEST_SESSION));
    renderGuarded();
    expect(screen.getByText("protected-content")).toBeInTheDocument();
  });
});
