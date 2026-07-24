/**
 * Component tests for the login page.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginPage } from "./LoginPage";
import { renderWithProviders, stubFetch } from "../../test/utils";
import type { TokenResponse } from "../../api/types";

const TOKEN: TokenResponse = {
  accessToken: "jwt-abc",
  tokenType: "Bearer",
  expiresIn: 3600,
  subject: "00000000-0000-0000-0000-000000000001",
  username: "employee",
  roles: ["EMPLOYEE"],
  permissions: ["ticket:read"],
  teams: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("LoginPage", () => {
  it("submits credentials and stores the session on success", async () => {
    const fetchMock = stubFetch([{ status: 200, json: TOKEN }]);
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { routerEntries: ["/login"] });

    await user.type(screen.getByLabelText("Имя пользователя"), "employee");
    await user.type(screen.getByLabelText("Пароль"), "changeme-dev-01");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => {
      expect(sessionStorage.getItem("mfo.auth.session")).toContain("jwt-abc");
    });

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/auth/login");
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse(init.body as string)).toEqual({
      username: "employee",
      password: "changeme-dev-01",
    });
  });

  it("shows an invalid-credentials message on 401", async () => {
    stubFetch([{ status: 401, json: { title: "Unauthorized", status: 401 } }]);
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { routerEntries: ["/login"] });

    await user.type(screen.getByLabelText("Имя пользователя"), "employee");
    await user.type(screen.getByLabelText("Пароль"), "wrong");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Неверное имя пользователя или пароль.",
    );
  });
});
