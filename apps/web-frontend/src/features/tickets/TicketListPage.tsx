/**
 * Appeal list and search page.
 *
 * Combines the search form, the results table, and pagination over the gateway search endpoint.
 * Applying filters resets to the first page. Loading, empty, and error states are shown explicitly;
 * each contracted gateway failure (400/401/403/404/409/413/422/429/5xx), a timeout, a network
 * failure, and an invalid response are mapped to a distinct localized message, with a bounded
 * Retry-After hint for 429 and a manual retry for transient failures. The diagnostic correlation id
 * is shown separately from the user message. Opening an individual appeal card is delivered in a
 * later subtask (01E-4).
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../../api/errors";
import { errorCorrelationId, errorMessageKey, retryAfterSeconds } from "../../api/errorMessages";
import { EMPTY_FORM_VALUES, toFilters, type TicketSearchFormValues } from "./searchValues";
import { TicketSearchForm } from "./TicketSearchForm";
import { TicketTable } from "./TicketTable";
import { useTicketSearch } from "./useTicketSearch";

/** Default page size for the appeal list. */
const DEFAULT_PAGE_SIZE = 20;

/**
 * Whether an error is an authentication/authorization failure that a manual retry cannot fix.
 *
 * Args:
 *   error: The query error.
 *
 * Returns:
 *   True for 401/403, which should not offer a retry.
 */
function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

/**
 * Render the appeal list and search page.
 *
 * Returns:
 *   The page element.
 */
export function TicketListPage(): React.JSX.Element {
  const { t } = useTranslation();
  const [applied, setApplied] = useState<TicketSearchFormValues>(EMPTY_FORM_VALUES);
  const [page, setPage] = useState(1);

  const filters = useMemo(() => toFilters(applied, page, DEFAULT_PAGE_SIZE), [applied, page]);
  const query = useTicketSearch(filters);

  const onApply = (values: TicketSearchFormValues): void => {
    setApplied(values);
    setPage(1);
  };

  const isForbidden = query.error instanceof ApiError && query.error.status === 403;
  const total = query.data?.page.total ?? 0;
  const items = query.data?.items ?? [];
  const hasNextPage = page * DEFAULT_PAGE_SIZE < total;

  // Message selection: 403 keeps a domain-specific message; a 429 with a bounded Retry-After shows
  // the wait hint; everything else maps by status/transport class.
  let errorMessage: string | null = null;
  let correlationId: string | null = null;
  if (query.isError) {
    const retry = retryAfterSeconds(query.error);
    if (isForbidden) {
      errorMessage = t("tickets.forbidden");
    } else if (retry !== null) {
      errorMessage = t("errors.rateLimitedRetry", { seconds: retry });
    } else {
      errorMessage = t(errorMessageKey(query.error));
    }
    correlationId = errorCorrelationId(query.error);
  }

  return (
    <section className="ticket-list-page">
      <h2>{t("tickets.title")}</h2>

      <TicketSearchForm onApply={onApply} />

      {query.isLoading ? <p role="status">{t("tickets.loading")}</p> : null}

      {errorMessage ? (
        <div className="form-error" role="alert">
          <p>{errorMessage}</p>
          {correlationId ? (
            <p className="error-correlation">{t("errors.correlation", { id: correlationId })}</p>
          ) : null}
          {!isAuthError(query.error) ? (
            <button type="button" onClick={() => void query.refetch()}>
              {t("common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {query.isSuccess && items.length === 0 ? <p role="status">{t("tickets.empty")}</p> : null}

      {items.length > 0 ? (
        <>
          <TicketTable items={items} />
          <nav className="pagination" aria-label={t("tickets.title")}>
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              {t("pagination.prev")}
            </button>
            <span>{t("pagination.summary", { page, total })}</span>
            <button type="button" onClick={() => setPage((p) => p + 1)} disabled={!hasNextPage}>
              {t("pagination.next")}
            </button>
          </nav>
        </>
      ) : null}
    </section>
  );
}
