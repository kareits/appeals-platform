/**
 * Component tests for the appeal results table, including XSS-safe rendering.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "../../i18n";
import { TicketTable } from "./TicketTable";
import type { TicketSummary } from "../../api/types";

function summary(overrides: Partial<TicketSummary> = {}): TicketSummary {
  return {
    id: "t-1",
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

describe("TicketTable", () => {
  it("renders appeal fields", () => {
    render(<TicketTable items={[summary()]} />);
    expect(screen.getByText("AP-2026-000001")).toBeInTheDocument();
    expect(screen.getByText("subject")).toBeInTheDocument();
  });

  it("renders an injection payload as inert text, not markup", () => {
    const payload = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>';
    render(<TicketTable items={[summary({ subject: payload })]} />);

    // The payload is shown verbatim as text (React escapes it).
    expect(screen.getByText(payload)).toBeInTheDocument();
    // No element from the payload was actually created in the document.
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect((window as unknown as Record<string, unknown>).__xss).toBeUndefined();
  });
});
