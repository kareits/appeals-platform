/**
 * Unit tests for the runtime response decoders (fail-closed validation).
 */
import { describe, expect, it } from "vitest";
import {
  SUPPORTED_ROLES,
  decodeAuthContext,
  decodePageMeta,
  decodePaginatedTickets,
  decodeProblem,
  decodeTicketSummary,
  decodeTokenResponse,
} from "./decoders";
import { ProtocolError } from "./errors";
import type { TicketSummary, TokenResponse } from "./types";

const UUID_A = "00000000-0000-0000-0000-000000000001";
const UUID_B = "00000000-0000-0000-0000-0000000000aa";

function validToken(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    accessToken: "jwt",
    tokenType: "Bearer",
    expiresIn: 3600,
    subject: UUID_A,
    username: "employee",
    roles: ["EMPLOYEE"],
    permissions: ["ticket:read"],
    teams: [],
    ...overrides,
  };
}

function validSummary(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: UUID_B,
    registrationNumber: "AP-2026-000001",
    subject: "subject",
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

describe("decodeTokenResponse", () => {
  it("accepts a valid token", () => {
    const token: TokenResponse = decodeTokenResponse(validToken());
    expect(token.accessToken).toBe("jwt");
    expect(token.roles).toEqual(["EMPLOYEE"]);
  });

  it("accepts every supported role", () => {
    const token = decodeTokenResponse(validToken({ roles: [...SUPPORTED_ROLES] }));
    expect(token.roles).toHaveLength(SUPPORTED_ROLES.length);
  });

  it("rejects an unknown role (fail closed)", () => {
    expect(() => decodeTokenResponse(validToken({ roles: ["SUPERADMIN"] }))).toThrow(ProtocolError);
  });

  it("rejects a missing access token", () => {
    const bad = validToken();
    delete bad.accessToken;
    expect(() => decodeTokenResponse(bad)).toThrow(ProtocolError);
  });

  it("rejects a non-Bearer token type", () => {
    expect(() => decodeTokenResponse(validToken({ tokenType: "Basic" }))).toThrow(ProtocolError);
  });

  it("rejects non-string permission entries", () => {
    expect(() => decodeTokenResponse(validToken({ permissions: [1, 2] }))).toThrow(ProtocolError);
  });

  it("rejects a non-UUID subject", () => {
    expect(() => decodeTokenResponse(validToken({ subject: "not-a-uuid" }))).toThrow(ProtocolError);
  });

  it("rejects a non-positive token lifetime", () => {
    expect(() => decodeTokenResponse(validToken({ expiresIn: 0 }))).toThrow(ProtocolError);
  });

  it("rejects non-UUID team identifiers", () => {
    expect(() => decodeTokenResponse(validToken({ teams: ["team-1"] }))).toThrow(ProtocolError);
  });
});

describe("decodeAuthContext", () => {
  it("accepts a valid context", () => {
    const ctx = decodeAuthContext({
      subject: UUID_A,
      username: "u",
      roles: ["EMPLOYEE"],
      permissions: [],
    });
    expect(ctx.username).toBe("u");
  });

  it("rejects a missing subject", () => {
    expect(() => decodeAuthContext({ username: "u", roles: [], permissions: [] })).toThrow(
      ProtocolError,
    );
  });

  it("rejects a non-UUID subject", () => {
    expect(() =>
      decodeAuthContext({ subject: "s", username: "u", roles: [], permissions: [] }),
    ).toThrow(ProtocolError);
  });
});

describe("decodeTicketSummary", () => {
  it("accepts a valid summary", () => {
    const summary: TicketSummary = decodeTicketSummary(validSummary());
    expect(summary.registrationNumber).toBe("AP-2026-000001");
  });

  it("rejects a missing required field", () => {
    const bad = validSummary();
    delete bad.registrationNumber;
    expect(() => decodeTicketSummary(bad)).toThrow(ProtocolError);
  });

  it("rejects a wrong-typed nullable field", () => {
    expect(() => decodeTicketSummary(validSummary({ contractNumber: 42 }))).toThrow(ProtocolError);
  });

  it("rejects a non-UUID id", () => {
    expect(() => decodeTicketSummary(validSummary({ id: "ticket-1" }))).toThrow(ProtocolError);
  });

  it("rejects a non-UUID nullable identifier", () => {
    expect(() => decodeTicketSummary(validSummary({ currentAssigneeId: "assignee" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects a malformed date-time", () => {
    expect(() => decodeTicketSummary(validSummary({ receivedAt: "2026-07-20" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects an offset-naive date-time", () => {
    expect(() =>
      decodeTicketSummary(validSummary({ registeredAt: "2026-07-20T09:00:00" })),
    ).toThrow(ProtocolError);
  });

  it.each([
    "2026-02-30T00:00:00Z", // February never has 30 days
    "2027-02-29T00:00:00Z", // 2027 is not a leap year
    "2026-13-01T00:00:00Z", // month out of range
    "2026-00-10T00:00:00Z", // month zero
    "2026-04-31T00:00:00Z", // April has 30 days
    "2026-01-32T00:00:00Z", // day out of range
    "2026-01-01T24:00:00Z", // hour out of range
    "2026-01-01T00:60:00Z", // minute out of range
    "2026-01-01T00:00:60Z", // second out of range
    "2026-01-01T00:00:00+99:00", // offset hour out of range
  ])("rejects the calendar/range-invalid date-time %s", (value) => {
    expect(() => decodeTicketSummary(validSummary({ receivedAt: value }))).toThrow(ProtocolError);
  });

  it.each([
    "2024-02-29T00:00:00Z", // valid leap day
    "2026-07-24T12:00:00.500Z", // fractional seconds
    "2026-07-24T12:00:00+05:00", // numeric offset
    "2026-12-31T23:59:59Z", // upper bounds of month/day/time
  ])("accepts the valid offset-aware date-time %s", (value) => {
    expect(decodeTicketSummary(validSummary({ receivedAt: value })).receivedAt).toBe(value);
  });
});

describe("decodePageMeta", () => {
  it("accepts sane bounds", () => {
    expect(decodePageMeta({ page: 1, pageSize: 20, total: 5 })).toEqual({
      page: 1,
      pageSize: 20,
      total: 5,
    });
  });

  it("rejects a zero page", () => {
    expect(() => decodePageMeta({ page: 0, pageSize: 20, total: 5 })).toThrow(ProtocolError);
  });

  it("rejects an oversized page size", () => {
    expect(() => decodePageMeta({ page: 1, pageSize: 1000, total: 5 })).toThrow(ProtocolError);
  });

  it("rejects a negative total", () => {
    expect(() => decodePageMeta({ page: 1, pageSize: 20, total: -1 })).toThrow(ProtocolError);
  });
});

describe("decodePaginatedTickets", () => {
  it("accepts a valid page", () => {
    const result = decodePaginatedTickets({
      items: [validSummary()],
      page: { page: 1, pageSize: 20, total: 1 },
    });
    expect(result.items).toHaveLength(1);
  });

  it("rejects items that are not an array", () => {
    expect(() =>
      decodePaginatedTickets({ items: {}, page: { page: 1, pageSize: 20, total: 0 } }),
    ).toThrow(ProtocolError);
  });

  it("rejects a malformed item", () => {
    expect(() =>
      decodePaginatedTickets({ items: [{ id: 1 }], page: { page: 1, pageSize: 20, total: 1 } }),
    ).toThrow(ProtocolError);
  });
});

describe("decodeProblem", () => {
  it("accepts a valid problem", () => {
    expect(decodeProblem({ title: "Bad", status: 400 })).toMatchObject({
      title: "Bad",
      status: 400,
    });
  });

  it("returns null for a non-problem body", () => {
    expect(decodeProblem({ foo: "bar" })).toBeNull();
    expect(decodeProblem("not json")).toBeNull();
    expect(decodeProblem(null)).toBeNull();
  });
});
