/**
 * Unit tests for the runtime response decoders (fail-closed validation).
 */
import { describe, expect, it } from "vitest";
import {
  SUPPORTED_ROLES,
  decodeApplicant,
  decodeAuthContext,
  decodeComment,
  decodeCommentList,
  decodePageMeta,
  decodePaginatedTickets,
  decodeProblem,
  decodeReferenceData,
  decodeTicketResponse,
  decodeTicketSummary,
  decodeTokenResponse,
  decodeWorkspace,
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

function validReferenceEntry(
  overrides: Partial<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    dictionaryType: "product",
    code: "MICROLOAN",
    displayNameRu: "Микрокредит",
    displayNameKk: null,
    sortOrder: 10,
    ...overrides,
  };
}

describe("decodeReferenceData", () => {
  it("accepts a valid reference-data envelope", () => {
    const result = decodeReferenceData({ entries: [validReferenceEntry()] });
    expect(result.entries).toHaveLength(1);
    expect(result.entries[0]!.code).toBe("MICROLOAN");
  });

  it("accepts a Kazakh display label when present", () => {
    const result = decodeReferenceData({
      entries: [validReferenceEntry({ displayNameKk: "Микрокредит" })],
    });
    expect(result.entries[0]!.displayNameKk).toBe("Микрокредит");
  });

  it("rejects entries that are not an array", () => {
    expect(() => decodeReferenceData({ entries: {} })).toThrow(ProtocolError);
  });

  it("rejects a missing required entry field", () => {
    const bad = validReferenceEntry();
    delete bad.displayNameRu;
    expect(() => decodeReferenceData({ entries: [bad] })).toThrow(ProtocolError);
  });

  it("rejects a non-integer sort order", () => {
    expect(() =>
      decodeReferenceData({ entries: [validReferenceEntry({ sortOrder: 1.5 })] }),
    ).toThrow(ProtocolError);
  });

  it("rejects a wrong-typed Kazakh label", () => {
    expect(() =>
      decodeReferenceData({ entries: [validReferenceEntry({ displayNameKk: 42 })] }),
    ).toThrow(ProtocolError);
  });
});

function validTicketResponse(
  overrides: Partial<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    id: UUID_B,
    registrationNumber: "AP-2026-000001",
    receivedAt: "2026-08-01T09:00:00Z",
    registeredAt: "2026-08-01T09:05:00Z",
    sourceChannelCode: "EMAIL",
    subject: "subject",
    description: "full appeal text",
    productCode: "MICROLOAN",
    classifierCode: "COMPLAINT",
    priorityCode: "NORMAL",
    currentStatusCode: "NEW",
    currentStageCode: "REGISTRATION",
    currentTeamId: null,
    currentAssigneeId: null,
    contractNumber: null,
    legalDueAt: null,
    internalDueAt: null,
    slaPolicyVersion: null,
    decisionCode: null,
    decisionSummary: null,
    decisionText: null,
    decisionAt: null,
    decisionBy: null,
    closureReasonCode: null,
    closedAt: null,
    responseSentAt: null,
    noResponseReason: null,
    retentionUntil: null,
    legalHold: false,
    isConfidential: false,
    version: 1,
    applicants: [],
    ...overrides,
  };
}

describe("decodeTicketResponse", () => {
  it("accepts a valid card", () => {
    const result = decodeTicketResponse(validTicketResponse());
    expect(result.registrationNumber).toBe("AP-2026-000001");
    expect(result.version).toBe(1);
  });

  it("rejects a non-UUID id", () => {
    expect(() => decodeTicketResponse(validTicketResponse({ id: "ticket-1" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects a non-boolean confidentiality flag", () => {
    expect(() => decodeTicketResponse(validTicketResponse({ isConfidential: "false" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects a non-integer version", () => {
    expect(() => decodeTicketResponse(validTicketResponse({ version: "1" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects a missing required field", () => {
    const bad = validTicketResponse();
    delete bad.registrationNumber;
    expect(() => decodeTicketResponse(bad)).toThrow(ProtocolError);
  });

  it("rejects a missing applicants array", () => {
    const bad = validTicketResponse();
    delete bad.applicants;
    expect(() => decodeTicketResponse(bad)).toThrow(ProtocolError);
  });

  it("rejects a calendar-impossible received-at instant", () => {
    expect(() =>
      decodeTicketResponse(validTicketResponse({ receivedAt: "2026-02-30T09:00:00Z" })),
    ).toThrow(ProtocolError);
  });

  it("accepts a valid retention date", () => {
    expect(
      decodeTicketResponse(validTicketResponse({ retentionUntil: "2031-08-01" })).retentionUntil,
    ).toBe("2031-08-01");
  });

  it("rejects a calendar-impossible retention date", () => {
    expect(() =>
      decodeTicketResponse(validTicketResponse({ retentionUntil: "2027-02-29" })),
    ).toThrow(ProtocolError);
  });

  it("validates an embedded applicant", () => {
    const card = decodeTicketResponse(
      validTicketResponse({
        applicants: [
          {
            id: UUID_A,
            applicantType: "CONSUMER",
            fullName: "Иванов Иван",
            identifierType: "IIN",
            identifierMasked: "******7890",
            email: null,
            phone: null,
            genderCode: null,
            birthDate: null,
            age: null,
            regionCode: null,
            dataSource: "MANUAL",
            representativeBasis: null,
          },
        ],
      }),
    );
    expect(card.applicants[0]?.identifierMasked).toBe("******7890");
  });
});

function validApplicant(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: UUID_A,
    applicantType: "CONSUMER",
    fullName: "Иванов Иван",
    identifierType: null,
    identifierMasked: null,
    email: null,
    phone: null,
    genderCode: null,
    birthDate: null,
    age: null,
    regionCode: null,
    dataSource: "APPEAL",
    representativeBasis: null,
    ...overrides,
  };
}

describe("decodeApplicant", () => {
  it("accepts a valid applicant", () => {
    expect(decodeApplicant(validApplicant()).applicantType).toBe("CONSUMER");
  });

  it("rejects an unknown applicant type", () => {
    expect(() => decodeApplicant(validApplicant({ applicantType: "OTHER" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects a non-integer age", () => {
    expect(() => decodeApplicant(validApplicant({ age: 3.5 }))).toThrow(ProtocolError);
  });

  it("accepts a valid birth date", () => {
    expect(decodeApplicant(validApplicant({ birthDate: "1990-02-28" })).birthDate).toBe(
      "1990-02-28",
    );
  });

  it("rejects a calendar-impossible birth date", () => {
    expect(() => decodeApplicant(validApplicant({ birthDate: "2026-02-30" }))).toThrow(
      ProtocolError,
    );
  });

  it("rejects a date-time where a plain date is expected", () => {
    expect(() => decodeApplicant(validApplicant({ birthDate: "1990-02-28T00:00:00Z" }))).toThrow(
      ProtocolError,
    );
  });
});

function validComment(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: UUID_A,
    ticketId: UUID_B,
    authorId: UUID_A,
    body: "a comment",
    createdAt: "2026-08-01T10:00:00Z",
    ...overrides,
  };
}

describe("decodeComment / decodeCommentList", () => {
  it("accepts a valid comment", () => {
    expect(decodeComment(validComment()).body).toBe("a comment");
  });

  it("rejects a comment with a non-UUID author", () => {
    expect(() => decodeComment(validComment({ authorId: "author" }))).toThrow(ProtocolError);
  });

  it("decodes a list of comments", () => {
    expect(decodeCommentList([validComment(), validComment()])).toHaveLength(2);
  });

  it("rejects a non-array comment list", () => {
    expect(() => decodeCommentList({})).toThrow(ProtocolError);
  });
});

function validWorkspace(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  const placeholder = { status: "not_implemented", data: null };
  return {
    ticketId: UUID_B,
    degraded: false,
    sections: {
      ticket: { status: "ok", data: validTicketResponse() },
      comments: { status: "ok", data: [validComment()] },
      process: placeholder,
      mail: placeholder,
      documents: placeholder,
    },
    ...overrides,
  };
}

describe("decodeWorkspace", () => {
  it("accepts a valid workspace envelope", () => {
    const workspace = decodeWorkspace(validWorkspace());
    expect(workspace.ticketId).toBe(UUID_B);
    expect(workspace.sections.ticket.status).toBe("ok");
    expect(workspace.sections.process.status).toBe("not_implemented");
  });

  it("accepts a degraded workspace with an unavailable comments section", () => {
    const workspace = decodeWorkspace(
      validWorkspace({
        degraded: true,
        sections: {
          ticket: { status: "ok", data: validTicketResponse() },
          comments: { status: "unavailable", data: null },
          process: { status: "not_implemented", data: null },
          mail: { status: "not_implemented", data: null },
          documents: { status: "not_implemented", data: null },
        },
      }),
    );
    expect(workspace.degraded).toBe(true);
    expect(workspace.sections.comments.status).toBe("unavailable");
    expect(workspace.sections.comments.data).toBeNull();
  });

  it("rejects an unknown section status", () => {
    expect(() =>
      decodeWorkspace(
        validWorkspace({
          sections: {
            ticket: { status: "broken", data: null },
            comments: { status: "ok", data: [] },
            process: { status: "not_implemented", data: null },
            mail: { status: "not_implemented", data: null },
            documents: { status: "not_implemented", data: null },
          },
        }),
      ),
    ).toThrow(ProtocolError);
  });

  it("rejects a section missing the required data field", () => {
    expect(() =>
      decodeWorkspace(
        validWorkspace({
          sections: {
            ticket: { status: "ok" },
            comments: { status: "ok", data: [] },
            process: { status: "not_implemented", data: null },
            mail: { status: "not_implemented", data: null },
            documents: { status: "not_implemented", data: null },
          },
        }),
      ),
    ).toThrow(ProtocolError);
  });

  it("rejects a non-ok section that still carries data", () => {
    expect(() =>
      decodeWorkspace(
        validWorkspace({
          sections: {
            ticket: { status: "ok", data: validTicketResponse() },
            comments: { status: "unavailable", data: [validComment()] },
            process: { status: "not_implemented", data: null },
            mail: { status: "not_implemented", data: null },
            documents: { status: "not_implemented", data: null },
          },
        }),
      ),
    ).toThrow(ProtocolError);
  });
});
