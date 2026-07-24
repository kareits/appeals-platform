/**
 * Wire-contract parity between the frontend transport projection and the committed BFF OpenAPI.
 *
 * The frontend types are a hand-maintained projection of `contracts/openapi/bff-service.v1.yaml`
 * (ADR-0009). This test parses the committed contract and asserts the operations, query filters,
 * role enum, and response schema fields the frontend depends on actually exist and match — so an
 * upstream contract change that would silently break decoding fails the build. It is a schema-level
 * comparison, not a path/operationId presence check.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { SUPPORTED_ROLES } from "./decoders";

// Resolve from the package root (Vitest's cwd) to the committed contract two levels up.
const contractPath = resolve(process.cwd(), "../../contracts/openapi/bff-service.v1.yaml");
/** A minimal OpenAPI property schema (3.1: `type` may be a union array including "null"). */
interface PropSchema {
  type?: string | string[];
  format?: string;
  items?: { type?: string; format?: string };
}

interface SchemaObject {
  properties?: Record<string, PropSchema>;
  required?: string[];
  enum?: string[];
}

const contract = parse(readFileSync(contractPath, "utf8")) as {
  paths: Record<string, Record<string, { parameters?: Array<{ name?: string; in?: string }> }>>;
  components: {
    schemas: Record<string, SchemaObject>;
    responses?: Record<string, { content?: Record<string, unknown> }>;
  };
};

const schemas = contract.components.schemas;

/** Decompose a possibly-nullable OpenAPI 3.1 type into its base type and nullability. */
function typeInfo(prop: PropSchema): { base: string | undefined; nullable: boolean } {
  const type = prop.type;
  if (Array.isArray(type)) {
    return { base: type.find((t) => t !== "null"), nullable: type.includes("null") };
  }
  return { base: type, nullable: false };
}

/** Assert a schema property's base type, nullability, and (optionally) format. */
function expectProp(
  schema: SchemaObject,
  name: string,
  expected: { type: string; nullable: boolean; format?: string },
): void {
  const prop = schema.properties?.[name];
  expect(prop, `property ${name} missing`).toBeDefined();
  const info = typeInfo(prop!);
  expect(info.base, `${name} base type`).toBe(expected.type);
  expect(info.nullable, `${name} nullability`).toBe(expected.nullable);
  if (expected.format) {
    expect(prop!.format, `${name} format`).toBe(expected.format);
  }
}

/** Filter and pagination query parameters the frontend sends to GET /tickets. */
const FRONTEND_TICKET_QUERY = [
  "registrationNumber",
  "identifierValue",
  "fullName",
  "contractNumber",
  "statusCode",
  "stageCode",
  "productCode",
  "classifierCode",
  "channelCode",
  "assigneeId",
  "teamId",
  "receivedFrom",
  "receivedTo",
  "registeredFrom",
  "registeredTo",
  "page",
  "pageSize",
];

/** Fields the frontend reads from each TicketSummary (required + nullable). */
const FRONTEND_SUMMARY_FIELDS = [
  "id",
  "registrationNumber",
  "subject",
  "currentStatusCode",
  "currentStageCode",
  "productCode",
  "classifierCode",
  "priorityCode",
  "contractNumber",
  "currentAssigneeId",
  "currentTeamId",
  "receivedAt",
  "registeredAt",
];

describe("BFF contract parity", () => {
  it("exposes the operations the frontend calls", () => {
    expect(contract.paths["/auth/login"]?.post).toBeDefined();
    expect(contract.paths["/tickets"]?.get).toBeDefined();
  });

  it("accepts every ticket query filter the frontend sends", () => {
    const params = contract.paths["/tickets"]!.get!.parameters ?? [];
    const queryNames = new Set(params.filter((p) => p.in === "query").map((p) => p.name));
    for (const name of FRONTEND_TICKET_QUERY) {
      expect(queryNames.has(name), `missing query parameter ${name}`).toBe(true);
    }
  });

  it("declares the same role set the frontend accepts", () => {
    expect(new Set(schemas.Role!.enum)).toEqual(new Set(SUPPORTED_ROLES));
  });

  it("requires the token fields the frontend decodes", () => {
    const required = new Set(schemas.TokenResponse!.required);
    for (const field of [
      "accessToken",
      "tokenType",
      "expiresIn",
      "subject",
      "username",
      "roles",
      "permissions",
      "teams",
    ]) {
      expect(required.has(field), `TokenResponse must require ${field}`).toBe(true);
    }
  });

  it("provides every TicketSummary field the frontend reads", () => {
    const properties = new Set(Object.keys(schemas.TicketSummary!.properties ?? {}));
    for (const field of FRONTEND_SUMMARY_FIELDS) {
      expect(properties.has(field), `TicketSummary must define ${field}`).toBe(true);
    }
    // The fields the frontend treats as required must be required by the contract too.
    const required = new Set(schemas.TicketSummary!.required);
    for (const field of ["id", "registrationNumber", "subject", "receivedAt", "registeredAt"]) {
      expect(required.has(field), `TicketSummary must require ${field}`).toBe(true);
    }
  });

  it("shapes the paginated envelope the frontend expects", () => {
    expect(new Set(schemas.PaginatedTickets!.required)).toEqual(new Set(["items", "page"]));
    expect(new Set(schemas.PageMeta!.required)).toEqual(new Set(["page", "pageSize", "total"]));
  });

  it("matches the token field types and formats the decoder enforces", () => {
    const token = schemas.TokenResponse!;
    expectProp(token, "subject", { type: "string", nullable: false, format: "uuid" });
    expectProp(token, "expiresIn", { type: "integer", nullable: false });
    const teams = token.properties?.teams;
    expect(teams?.type).toBe("array");
    expect(teams?.items?.format).toBe("uuid");
  });

  it("matches the TicketSummary field types, formats, and nullability the decoder enforces", () => {
    const summary = schemas.TicketSummary!;
    expectProp(summary, "id", { type: "string", nullable: false, format: "uuid" });
    expectProp(summary, "registrationNumber", { type: "string", nullable: false });
    expectProp(summary, "receivedAt", { type: "string", nullable: false, format: "date-time" });
    expectProp(summary, "registeredAt", { type: "string", nullable: false, format: "date-time" });
    expectProp(summary, "contractNumber", { type: "string", nullable: true });
    expectProp(summary, "currentAssigneeId", { type: "string", nullable: true, format: "uuid" });
    expectProp(summary, "currentTeamId", { type: "string", nullable: true, format: "uuid" });
  });

  it("matches the PageMeta integer types the decoder enforces", () => {
    const meta = schemas.PageMeta!;
    expectProp(meta, "page", { type: "integer", nullable: false });
    expectProp(meta, "pageSize", { type: "integer", nullable: false });
    expectProp(meta, "total", { type: "integer", nullable: false });
  });

  it("serves errors as application/problem+json with the Problem schema the client enforces", () => {
    // The client accepts an RFC 7807 error only under an exact application/problem+json media type;
    // the contract must declare exactly that (and not application/json) for its error responses.
    const problemResponse = contract.components.responses?.Problem;
    expect(problemResponse?.content?.["application/problem+json"]).toBeDefined();
    expect(problemResponse?.content?.["application/json"]).toBeUndefined();

    const problem = schemas.Problem!;
    expect(new Set(problem.required)).toEqual(new Set(["title", "status"]));
    expectProp(problem, "title", { type: "string", nullable: false });
    expectProp(problem, "status", { type: "integer", nullable: false });
    expectProp(problem, "detail", { type: "string", nullable: true });
    expectProp(problem, "instance", { type: "string", nullable: true });
  });
});
