/**
 * Unit tests for the registration-form validation and request mapping.
 *
 * These prove the DoD 01E-3 invariants without a network: required fields are validated, and every
 * demographic ("conditional") field left blank is sent as null rather than blocking registration.
 */
import { describe, expect, it } from "vitest";
import {
  EMPTY_REGISTER_VALUES,
  buildCreateRequest,
  type RegisterFormValues,
} from "./registerValues";

/** Build a minimally valid set of form values (all required fields supplied, demographics blank). */
function validValues(overrides: Partial<RegisterFormValues> = {}): RegisterFormValues {
  return {
    ...EMPTY_REGISTER_VALUES,
    receivedAt: "2026-08-01T09:00",
    sourceChannelCode: "EMAIL",
    subject: "Restructuring request",
    description: "Full appeal text",
    productCode: "MICROLOAN",
    classifierCode: "RESTRUCTURING",
    priorityCode: "NORMAL",
    ...overrides,
  };
}

describe("buildCreateRequest", () => {
  it("flags every missing required field and yields no request", () => {
    const { errors, request } = buildCreateRequest(EMPTY_REGISTER_VALUES);

    expect(request).toBeNull();
    expect(errors).toMatchObject({
      receivedAt: "required",
      sourceChannelCode: "required",
      subject: "required",
      description: "required",
      productCode: "required",
      classifierCode: "required",
      priorityCode: "required",
    });
  });

  it("builds a request with blank conditional fields sent as null", () => {
    const { errors, request } = buildCreateRequest(validValues());

    expect(errors).toEqual({});
    expect(request).not.toBeNull();
    expect(request!.receivedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/);
    expect(request!.contractNumber).toBeNull();
    expect(request!.representative).toBeNull();
    expect(request!.isConfidential).toBe(false);
    expect(request!.applicant).toMatchObject({
      applicantType: "CONSUMER",
      dataSource: "MANUAL",
      fullName: null,
      identifierType: null,
      identifierValue: null,
      email: null,
      phone: null,
      genderCode: null,
      birthDate: null,
      age: null,
      regionCode: null,
      representativeBasis: null,
    });
  });

  it("maps supplied demographics and a numeric age", () => {
    const { request } = buildCreateRequest(
      validValues({
        applicant: {
          ...EMPTY_REGISTER_VALUES.applicant,
          fullName: "  Иванов Иван  ",
          identifierType: "IIN",
          identifierValue: "900101300123",
          age: "35",
        },
      }),
    );

    expect(request!.applicant.fullName).toBe("Иванов Иван");
    expect(request!.applicant.identifierType).toBe("IIN");
    expect(request!.applicant.identifierValue).toBe("900101300123");
    expect(request!.applicant.age).toBe(35);
  });

  it("rejects a non-numeric or out-of-range age", () => {
    expect(buildCreateRequest(validValues({ applicant: age("abc") })).errors["applicant.age"]).toBe(
      "invalidAge",
    );
    expect(buildCreateRequest(validValues({ applicant: age("200") })).errors["applicant.age"]).toBe(
      "invalidAge",
    );
  });

  it("requires an identifier type and value together (or neither)", () => {
    const typeOnly = buildCreateRequest(
      validValues({
        applicant: { ...EMPTY_REGISTER_VALUES.applicant, identifierType: "IIN" },
      }),
    );
    expect(typeOnly.errors["applicant.identifierValue"]).toBe("identifierPair");

    const valueOnly = buildCreateRequest(
      validValues({
        applicant: { ...EMPTY_REGISTER_VALUES.applicant, identifierValue: "900101300123" },
      }),
    );
    expect(valueOnly.errors["applicant.identifierValue"]).toBe("identifierPair");
  });

  it("includes the representative as a REPRESENTATIVE party when enabled", () => {
    const { request } = buildCreateRequest(
      validValues({
        includeRepresentative: true,
        representative: {
          ...EMPTY_REGISTER_VALUES.representative,
          fullName: "Петров Пётр",
          representativeBasis: "Доверенность №1",
        },
      }),
    );

    expect(request!.representative).not.toBeNull();
    expect(request!.representative!.applicantType).toBe("REPRESENTATIVE");
    expect(request!.representative!.fullName).toBe("Петров Пётр");
    expect(request!.representative!.representativeBasis).toBe("Доверенность №1");
  });

  it("rejects an unparseable received-at value", () => {
    const { errors, request } = buildCreateRequest(validValues({ receivedAt: "not-a-date" }));
    expect(errors.receivedAt).toBe("invalidReceivedAt");
    expect(request).toBeNull();
  });

  it.each(["2026-02-30T09:00", "2026-13-01T09:00", "2027-02-29T09:00", "2026-04-31T09:00"])(
    "rejects the calendar-impossible received-at value %s instead of rolling it over",
    (receivedAt) => {
      const { errors, request } = buildCreateRequest(validValues({ receivedAt }));
      expect(errors.receivedAt).toBe("invalidReceivedAt");
      expect(request).toBeNull();
    },
  );

  it("accepts a real leap-day received-at value", () => {
    // 2028 is a leap year, so 29 February is a real date and must be accepted (not rejected). The
    // exact UTC value depends on the runner's timezone, so only the ISO shape is asserted.
    const { errors, request } = buildCreateRequest(validValues({ receivedAt: "2028-02-29T09:00" }));
    expect(errors.receivedAt).toBeUndefined();
    expect(request).not.toBeNull();
    expect(request!.receivedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/);
  });

  it("rejects a two-digit year that JavaScript maps into 1900-1999", () => {
    // new Date(99, ...) yields 1999; without a round-trip guard "0099-06-15T09:00" would be sent as
    // a 1999 instant. This case is timezone-independent (mid-June, mid-day).
    const { errors, request } = buildCreateRequest(validValues({ receivedAt: "0099-06-15T09:00" }));
    expect(errors.receivedAt).toBe("invalidReceivedAt");
    expect(request).toBeNull();
  });

  it("rejects a local wall-clock time that does not exist on a DST spring-forward boundary", () => {
    // In America/New_York, 2028-03-12 02:30 falls in the spring-forward gap (02:00 -> 03:00); Date
    // rolls it to 03:30. Pin the timezone deterministically for this assertion, then restore it.
    const previousTz = process.env.TZ;
    process.env.TZ = "America/New_York";
    try {
      const { errors, request } = buildCreateRequest(
        validValues({ receivedAt: "2028-03-12T02:30" }),
      );
      expect(errors.receivedAt).toBe("invalidReceivedAt");
      expect(request).toBeNull();
    } finally {
      // Restore exactly: assigning `undefined` would store the string "undefined" (interpreted as
      // GMT), leaking a wrong timezone into other tests, so an originally-absent variable is deleted.
      if (previousTz === undefined) {
        delete process.env.TZ;
      } else {
        process.env.TZ = previousTz;
      }
    }
  });
});

/** Build applicant values with a given age string for the age-validation cases. */
function age(value: string): RegisterFormValues["applicant"] {
  return { ...EMPTY_REGISTER_VALUES.applicant, age: value };
}
