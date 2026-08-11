/**
 * Unit tests for the appeal-card command value builders.
 *
 * These cover the client-side validation and request mapping for the edit, classify, decision, and
 * close commands: required-field enforcement, the "changed fields only" update, and the regulatory
 * close rule (a reason plus either a valid response date or a recorded reason for its absence).
 */
import { describe, expect, it } from "vitest";
import {
  buildClassifyRequest,
  buildCloseRequest,
  buildDecisionRequest,
  buildUpdateRequest,
  type CloseFormValues,
  type EditFormValues,
} from "./cardCommandValues";

const ORIGINAL_EDIT: EditFormValues = {
  subject: "Original subject",
  description: "Original description",
  sourceChannelCode: "EMAIL",
  contractNumber: "C-1",
};

describe("buildUpdateRequest", () => {
  it("includes only the fields that changed", () => {
    const values: EditFormValues = { ...ORIGINAL_EDIT, subject: "New subject" };
    const { errors, request } = buildUpdateRequest(values, ORIGINAL_EDIT, 3);
    expect(errors).toEqual({});
    expect(request).toEqual({ expectedVersion: 3, subject: "New subject" });
  });

  it("sends a blank contract number as null (clearing it)", () => {
    const values: EditFormValues = { ...ORIGINAL_EDIT, contractNumber: "  " };
    const { request } = buildUpdateRequest(values, ORIGINAL_EDIT, 2);
    expect(request).toEqual({ expectedVersion: 2, contractNumber: null });
  });

  it("rejects a blank required field", () => {
    const values: EditFormValues = { ...ORIGINAL_EDIT, subject: "   " };
    const { errors, request } = buildUpdateRequest(values, ORIGINAL_EDIT, 1);
    expect(errors.subject).toBe("required");
    expect(request).toBeNull();
  });

  it("reports no changes when nothing differs", () => {
    const { errors, request } = buildUpdateRequest({ ...ORIGINAL_EDIT }, ORIGINAL_EDIT, 1);
    expect(errors.form).toBe("noChanges");
    expect(request).toBeNull();
  });
});

describe("buildClassifyRequest", () => {
  it("builds a full classification", () => {
    const { errors, request } = buildClassifyRequest(
      { productCode: "MICROLOAN", classifierCode: "COMPLAINT", priorityCode: "HIGH" },
      4,
    );
    expect(errors).toEqual({});
    expect(request).toEqual({
      expectedVersion: 4,
      productCode: "MICROLOAN",
      classifierCode: "COMPLAINT",
      priorityCode: "HIGH",
    });
  });

  it("rejects a missing code", () => {
    const { errors, request } = buildClassifyRequest(
      { productCode: "", classifierCode: "COMPLAINT", priorityCode: "HIGH" },
      1,
    );
    expect(errors.productCode).toBe("required");
    expect(request).toBeNull();
  });
});

describe("buildDecisionRequest", () => {
  it("builds a decision and sends a blank summary as null", () => {
    const { errors, request } = buildDecisionRequest(
      { decisionCode: "SATISFIED", decisionSummary: "  ", decisionText: "Full decision text" },
      5,
    );
    expect(errors).toEqual({});
    expect(request).toEqual({
      expectedVersion: 5,
      decisionCode: "SATISFIED",
      decisionSummary: null,
      decisionText: "Full decision text",
    });
  });

  it("requires a code and full text", () => {
    const { errors, request } = buildDecisionRequest(
      { decisionCode: "", decisionSummary: "", decisionText: "" },
      1,
    );
    expect(errors.decisionCode).toBe("required");
    expect(errors.decisionText).toBe("required");
    expect(request).toBeNull();
  });
});

describe("buildCloseRequest", () => {
  const withResponse: CloseFormValues = {
    closureReasonCode: "RESOLVED",
    responseSentAt: "2026-08-05T10:00",
    noResponseReason: "",
  };

  it("builds a closure with a response date (converted to a UTC instant)", () => {
    const { errors, request } = buildCloseRequest(withResponse, 6);
    expect(errors).toEqual({});
    expect(request?.closureReasonCode).toBe("RESOLVED");
    expect(request?.responseSentAt).toMatch(/^2026-08-05T\d{2}:00:00/);
    expect(request?.noResponseReason).toBeNull();
    expect(request?.expectedVersion).toBe(6);
  });

  it("builds a closure with a no-response reason instead of a date", () => {
    const { errors, request } = buildCloseRequest(
      { closureReasonCode: "RESOLVED", responseSentAt: "", noResponseReason: "No contact given" },
      1,
    );
    expect(errors).toEqual({});
    expect(request?.responseSentAt).toBeNull();
    expect(request?.noResponseReason).toBe("No contact given");
  });

  it("requires a closure reason", () => {
    const { errors, request } = buildCloseRequest({ ...withResponse, closureReasonCode: "" }, 1);
    expect(errors.closureReasonCode).toBe("required");
    expect(request).toBeNull();
  });

  it("requires a response date or a recorded reason", () => {
    const { errors, request } = buildCloseRequest(
      { closureReasonCode: "RESOLVED", responseSentAt: "", noResponseReason: "" },
      1,
    );
    expect(errors.response).toBe("responseOrReason");
    expect(request).toBeNull();
  });

  it("rejects a calendar-impossible response date", () => {
    const { errors, request } = buildCloseRequest(
      { closureReasonCode: "RESOLVED", responseSentAt: "2026-02-30T10:00", noResponseReason: "" },
      1,
    );
    expect(errors.responseSentAt).toBe("invalidDateTime");
    expect(request).toBeNull();
  });
});
