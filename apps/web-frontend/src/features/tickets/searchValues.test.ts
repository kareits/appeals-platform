/**
 * Unit tests for the search-value mapping.
 */
import { describe, expect, it } from "vitest";
import { EMPTY_FORM_VALUES, toFilters } from "./searchValues";

describe("toFilters", () => {
  it("omits blank fields and applies pagination", () => {
    const filters = toFilters(EMPTY_FORM_VALUES, 2, 20);
    expect(filters).toEqual({
      registrationNumber: undefined,
      fullName: undefined,
      identifierValue: undefined,
      contractNumber: undefined,
      statusCode: undefined,
      stageCode: undefined,
      productCode: undefined,
      classifierCode: undefined,
      channelCode: undefined,
      receivedFrom: undefined,
      receivedTo: undefined,
      registeredFrom: undefined,
      registeredTo: undefined,
      page: 2,
      pageSize: 20,
    });
  });

  it("trims text filters", () => {
    const filters = toFilters(
      { ...EMPTY_FORM_VALUES, registrationNumber: "  AP-2026-000001  " },
      1,
      20,
    );
    expect(filters.registrationNumber).toBe("AP-2026-000001");
  });

  it("widens date filters to inclusive UTC instants", () => {
    const filters = toFilters(
      {
        ...EMPTY_FORM_VALUES,
        receivedFrom: "2026-07-01",
        receivedTo: "2026-07-31",
      },
      1,
      20,
    );
    expect(filters.receivedFrom).toBe("2026-07-01T00:00:00Z");
    expect(filters.receivedTo).toBe("2026-07-31T23:59:59Z");
  });
});
