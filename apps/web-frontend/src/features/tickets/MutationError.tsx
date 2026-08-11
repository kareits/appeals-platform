/**
 * Shared presentation of a card-command mutation error.
 *
 * Maps an API/transport error to a safe localized message (never rendering raw server text) and
 * shows the diagnostic correlation id separately from the user copy. Used by every card-command form
 * so they present failures consistently.
 */
import { useTranslation } from "react-i18next";
import { errorCorrelationId, errorMessageKey } from "../../api/errorMessages";

/** Props for the mutation-error banner. */
export interface MutationErrorProps {
  /** The error thrown by the mutation, or null/undefined when there is none. */
  error: unknown;
}

/**
 * Render a localized error banner for a failed card command.
 *
 * Args:
 *   props: The mutation error to present.
 *
 * Returns:
 *   The error banner, or null when there is no error.
 */
export function MutationError({ error }: MutationErrorProps): React.JSX.Element | null {
  const { t } = useTranslation();
  if (error === null || error === undefined) {
    return null;
  }
  const correlationId = errorCorrelationId(error);
  return (
    <div className="form-error" role="alert">
      <p>{t(errorMessageKey(error))}</p>
      {correlationId ? (
        <p className="error-correlation">{t("errors.correlation", { id: correlationId })}</p>
      ) : null}
    </div>
  );
}
