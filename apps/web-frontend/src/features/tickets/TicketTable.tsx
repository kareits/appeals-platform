/**
 * Presentational table of appeal search results.
 *
 * Renders a row per appeal summary with localized column headers and formatted timestamps. It is a
 * pure presentational component (no data fetching) so it is straightforward to test in isolation.
 */
import { useTranslation } from "react-i18next";
import type { TicketSummary } from "../../api/types";
import { formatDateTime } from "../../lib/format";

/** Props for the ticket table. */
export interface TicketTableProps {
  /** The appeal summaries to render. */
  items: TicketSummary[];
}

/**
 * Render the appeal results table.
 *
 * Args:
 *   props: The appeal summaries to display.
 *
 * Returns:
 *   The table element.
 */
export function TicketTable({ items }: TicketTableProps): React.JSX.Element {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "ru";

  return (
    <table className="ticket-table">
      <thead>
        <tr>
          <th>{t("tickets.table.registrationNumber")}</th>
          <th>{t("tickets.table.subject")}</th>
          <th>{t("tickets.table.status")}</th>
          <th>{t("tickets.table.stage")}</th>
          <th>{t("tickets.table.product")}</th>
          <th>{t("tickets.table.classifier")}</th>
          <th>{t("tickets.table.priority")}</th>
          <th>{t("tickets.table.receivedAt")}</th>
          <th>{t("tickets.table.registeredAt")}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((ticket) => (
          <tr key={ticket.id}>
            <td>{ticket.registrationNumber}</td>
            <td>{ticket.subject}</td>
            <td>{ticket.currentStatusCode}</td>
            <td>{ticket.currentStageCode}</td>
            <td>{ticket.productCode}</td>
            <td>{ticket.classifierCode}</td>
            <td>{ticket.priorityCode}</td>
            <td>{formatDateTime(ticket.receivedAt, locale)}</td>
            <td>{formatDateTime(ticket.registeredAt, locale)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
