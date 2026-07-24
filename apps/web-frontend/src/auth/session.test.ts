/**
 * Unit tests for session persistence and fail-closed restoration.
 */
import { afterEach, describe, expect, it } from "vitest";
import { clearSession, loadSession, saveSession, sessionFromToken, type Session } from "./session";
import type { TokenResponse } from "../api/types";

const STORAGE_KEY = "mfo.auth.session";

const SESSION: Session = {
  accessToken: "jwt",
  subject: "00000000-0000-0000-0000-000000000001",
  username: "employee",
  roles: ["EMPLOYEE"],
  permissions: ["ticket:read"],
};

afterEach(() => {
  sessionStorage.clear();
});

describe("sessionFromToken", () => {
  it("projects the token claims into a session", () => {
    const token: TokenResponse = {
      accessToken: "jwt",
      tokenType: "Bearer",
      expiresIn: 3600,
      subject: "00000000-0000-0000-0000-000000000001",
      username: "employee",
      roles: ["EMPLOYEE"],
      permissions: ["ticket:read"],
      teams: [],
    };
    expect(sessionFromToken(token)).toEqual(SESSION);
  });
});

describe("saveSession / loadSession", () => {
  it("round-trips a valid session", () => {
    saveSession(SESSION);
    expect(loadSession()).toEqual(SESSION);
  });

  it("returns null when nothing is stored", () => {
    expect(loadSession()).toBeNull();
  });

  it("returns null for invalid JSON", () => {
    sessionStorage.setItem(STORAGE_KEY, "{not-json");
    expect(loadSession()).toBeNull();
  });

  it.each([
    ["missing accessToken", { subject: "s", username: "u", roles: [], permissions: [] }],
    [
      "empty accessToken",
      { accessToken: "", subject: "s", username: "u", roles: [], permissions: [] },
    ],
    ["missing subject", { accessToken: "j", username: "u", roles: [], permissions: [] }],
    [
      "non-array roles",
      { accessToken: "j", subject: "s", username: "u", roles: "x", permissions: [] },
    ],
    [
      "non-string permission",
      { accessToken: "j", subject: "s", username: "u", roles: [], permissions: [1] },
    ],
    [
      "unknown role",
      {
        accessToken: "j",
        subject: "00000000-0000-0000-0000-000000000001",
        username: "u",
        roles: ["SUPERADMIN"],
        permissions: [],
      },
    ],
    [
      "non-UUID subject (all else valid)",
      {
        accessToken: "j",
        subject: "not-a-uuid",
        username: "u",
        roles: ["EMPLOYEE"],
        permissions: ["ticket:read"],
      },
    ],
  ])("returns null for a malformed session (%s)", (_label, stored) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    expect(loadSession()).toBeNull();
  });
});

describe("clearSession", () => {
  it("removes the stored session", () => {
    saveSession(SESSION);
    clearSession();
    expect(loadSession()).toBeNull();
  });
});
