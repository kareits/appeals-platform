/**
 * Appeal-card command forms: edit details, re-classify, record decision, close, and legal hold.
 *
 * Each form is rendered by the card page only when the caller holds the matching permission
 * (`ticket:update`/`classify`/`decide`/`close`/`legal_hold`); first-line read-only users therefore
 * see none of them. Client-side validation lives in `cardCommandValues` and mirrors the regulatory
 * rules for immediate feedback, while the gateway and Ticket Service remain the authority. Every form
 * carries the card's current `version` as `expectedVersion` for optimistic locking; a stale version
 * surfaces a 409 conflict. The card page remounts these forms (keyed by version) after any successful
 * card mutation, so their local state resets to the refreshed card.
 */
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button, Dialog } from "../../components/ui";
import type { ReferenceEntry, TicketResponse } from "../../api/types";
import {
  buildClassifyRequest,
  buildCloseRequest,
  buildDecisionRequest,
  buildUpdateRequest,
  type CardErrorCode,
  type CardErrors,
  type ClassifyFormValues,
  type CloseFormValues,
  type DecisionFormValues,
  type EditFormValues,
} from "./cardCommandValues";
import { MutationError } from "./MutationError";
import { entryLabel, optionsOfType } from "./referenceLabels";
import {
  useClassifyTicket,
  useCloseTicket,
  useRecordDecision,
  useSetLegalHold,
  useUpdateTicket,
} from "./useTicketCommands";

/** Props shared by the card command forms. */
interface CommandFormProps {
  /** The current appeal card (source of `expectedVersion` and prefilled values). */
  card: TicketResponse;
  /** The active reference entries, for the select options. */
  entries: ReferenceEntry[];
}

/**
 * Localize a card validation error code.
 *
 * Args:
 *   t: The translation function.
 *   code: The error code, or undefined when the field is valid.
 *
 * Returns:
 *   The localized message, or null when there is no error.
 */
function cardError(t: (key: string) => string, code: CardErrorCode | undefined): string | null {
  return code ? t(`card.error.${code}`) : null;
}

/** Props for the reusable reference-dictionary select. */
interface ReferenceSelectProps {
  /** The input id (also used for the label association). */
  id: string;
  /** The already-localized field label. */
  label: string;
  /** The dictionary type whose active entries are offered. */
  type: string;
  /** The active reference entries. */
  entries: ReferenceEntry[];
  /** The currently selected code. */
  value: string;
  /** Whether the field is required (renders the required marker). */
  required: boolean;
  /** The already-localized validation error, or null. */
  error: string | null;
  /** Called with the new code when the selection changes. */
  onChange: (value: string) => void;
}

/**
 * Render a labelled select populated from a reference dictionary.
 *
 * Args:
 *   props: The field id/label, dictionary type, entries, value, and change handler.
 *
 * Returns:
 *   The labelled select element.
 */
function ReferenceSelect({
  id,
  label,
  type,
  entries,
  value,
  required,
  error,
  onChange,
}: ReferenceSelectProps): React.JSX.Element {
  const { t, i18n } = useTranslation();
  const preferKazakh = (i18n.resolvedLanguage ?? "ru").startsWith("kk");
  return (
    <label htmlFor={id}>
      <span>
        {label} {required ? <abbr title={t("card.required")}>*</abbr> : null}
      </span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error !== null}
      >
        <option value="">{t("card.selectPlaceholder")}</option>
        {optionsOfType(entries, type).map((entry) => (
          <option key={entry.code} value={entry.code}>
            {entryLabel(entry, preferKazakh)}
          </option>
        ))}
      </select>
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}

/**
 * Render the edit-details form (subject, description, intake channel, contract number).
 *
 * Args:
 *   props: The current card and reference entries.
 *
 * Returns:
 *   The edit-details form element.
 */
export function EditDetailsForm({ card, entries }: CommandFormProps): React.JSX.Element {
  const { t } = useTranslation();
  const original: EditFormValues = {
    subject: card.subject,
    description: card.description,
    sourceChannelCode: card.sourceChannelCode,
    contractNumber: card.contractNumber ?? "",
  };
  const [values, setValues] = useState<EditFormValues>(original);
  const [errors, setErrors] = useState<CardErrors>({});
  const [saved, setSaved] = useState(false);
  const mutation = useUpdateTicket(card.id);

  const set = <K extends keyof EditFormValues>(field: K, value: string): void => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const { errors: found, request } = buildUpdateRequest(values, original, card.version);
    setErrors(found);
    if (request === null) {
      return;
    }
    mutation.mutate(request, { onSuccess: () => setSaved(true) });
  };

  return (
    <form className="card-command" onSubmit={onSubmit} aria-label={t("card.edit.title")}>
      <h3>{t("card.edit.title")}</h3>
      <label htmlFor="edit-subject">
        <span>
          {t("card.field.subject")} <abbr title={t("card.required")}>*</abbr>
        </span>
        <input
          id="edit-subject"
          value={values.subject}
          onChange={(event) => set("subject", event.target.value)}
          aria-invalid={cardError(t, errors.subject) !== null}
        />
        {cardError(t, errors.subject) ? (
          <span className="field-error">{cardError(t, errors.subject)}</span>
        ) : null}
      </label>
      <label htmlFor="edit-description">
        <span>
          {t("card.field.description")} <abbr title={t("card.required")}>*</abbr>
        </span>
        <textarea
          id="edit-description"
          value={values.description}
          onChange={(event) => set("description", event.target.value)}
          aria-invalid={cardError(t, errors.description) !== null}
        />
        {cardError(t, errors.description) ? (
          <span className="field-error">{cardError(t, errors.description)}</span>
        ) : null}
      </label>
      <ReferenceSelect
        id="edit-sourceChannelCode"
        label={t("card.field.sourceChannelCode")}
        type="channel"
        entries={entries}
        value={values.sourceChannelCode}
        required
        error={cardError(t, errors.sourceChannelCode)}
        onChange={(value) => set("sourceChannelCode", value)}
      />
      <label htmlFor="edit-contractNumber">
        <span>{t("card.field.contractNumber")}</span>
        <input
          id="edit-contractNumber"
          value={values.contractNumber}
          onChange={(event) => set("contractNumber", event.target.value)}
        />
      </label>
      {cardError(t, errors.form) ? (
        <p className="field-error" role="alert">
          {cardError(t, errors.form)}
        </p>
      ) : null}
      {mutation.isError ? <MutationError error={mutation.error} /> : null}
      {saved ? (
        <p className="form-success" role="status">
          {t("card.edit.success")}
        </p>
      ) : null}
      <Button type="submit" variant="primary" disabled={mutation.isPending}>
        {mutation.isPending ? t("card.edit.submitting") : t("card.edit.submit")}
      </Button>
    </form>
  );
}

/**
 * Render the re-classify form (product, classifier, priority).
 *
 * Args:
 *   props: The current card and reference entries.
 *
 * Returns:
 *   The classify form element.
 */
export function ClassifyForm({ card, entries }: CommandFormProps): React.JSX.Element {
  const { t } = useTranslation();
  const [values, setValues] = useState<ClassifyFormValues>({
    productCode: card.productCode,
    classifierCode: card.classifierCode,
    priorityCode: card.priorityCode,
  });
  const [errors, setErrors] = useState<CardErrors>({});
  const [saved, setSaved] = useState(false);
  const mutation = useClassifyTicket(card.id);

  const set = <K extends keyof ClassifyFormValues>(field: K, value: string): void => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const { errors: found, request } = buildClassifyRequest(values, card.version);
    setErrors(found);
    if (request === null) {
      return;
    }
    mutation.mutate(request, { onSuccess: () => setSaved(true) });
  };

  return (
    <form className="card-command" onSubmit={onSubmit} aria-label={t("card.classify.title")}>
      <h3>{t("card.classify.title")}</h3>
      <ReferenceSelect
        id="classify-productCode"
        label={t("card.field.productCode")}
        type="product"
        entries={entries}
        value={values.productCode}
        required
        error={cardError(t, errors.productCode)}
        onChange={(value) => set("productCode", value)}
      />
      <ReferenceSelect
        id="classify-classifierCode"
        label={t("card.field.classifierCode")}
        type="classifier"
        entries={entries}
        value={values.classifierCode}
        required
        error={cardError(t, errors.classifierCode)}
        onChange={(value) => set("classifierCode", value)}
      />
      <ReferenceSelect
        id="classify-priorityCode"
        label={t("card.field.priorityCode")}
        type="priority"
        entries={entries}
        value={values.priorityCode}
        required
        error={cardError(t, errors.priorityCode)}
        onChange={(value) => set("priorityCode", value)}
      />
      {mutation.isError ? <MutationError error={mutation.error} /> : null}
      {saved ? (
        <p className="form-success" role="status">
          {t("card.classify.success")}
        </p>
      ) : null}
      <Button type="submit" variant="primary" disabled={mutation.isPending}>
        {mutation.isPending ? t("card.classify.submitting") : t("card.classify.submit")}
      </Button>
    </form>
  );
}

/**
 * Render the decision form (decision code, optional summary, full text).
 *
 * Args:
 *   props: The current card and reference entries.
 *
 * Returns:
 *   The decision form element.
 */
export function DecisionForm({ card, entries }: CommandFormProps): React.JSX.Element {
  const { t } = useTranslation();
  const [values, setValues] = useState<DecisionFormValues>({
    decisionCode: card.decisionCode ?? "",
    decisionSummary: card.decisionSummary ?? "",
    decisionText: card.decisionText ?? "",
  });
  const [errors, setErrors] = useState<CardErrors>({});
  const [saved, setSaved] = useState(false);
  const mutation = useRecordDecision(card.id);

  const set = <K extends keyof DecisionFormValues>(field: K, value: string): void => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const { errors: found, request } = buildDecisionRequest(values, card.version);
    setErrors(found);
    if (request === null) {
      return;
    }
    mutation.mutate(request, { onSuccess: () => setSaved(true) });
  };

  return (
    <form className="card-command" onSubmit={onSubmit} aria-label={t("card.decision.title")}>
      <h3>{t("card.decision.title")}</h3>
      <ReferenceSelect
        id="decision-decisionCode"
        label={t("card.field.decisionCode")}
        type="decision"
        entries={entries}
        value={values.decisionCode}
        required
        error={cardError(t, errors.decisionCode)}
        onChange={(value) => set("decisionCode", value)}
      />
      <label htmlFor="decision-decisionSummary">
        <span>{t("card.field.decisionSummary")}</span>
        <input
          id="decision-decisionSummary"
          value={values.decisionSummary}
          onChange={(event) => set("decisionSummary", event.target.value)}
        />
      </label>
      <label htmlFor="decision-decisionText">
        <span>
          {t("card.field.decisionText")} <abbr title={t("card.required")}>*</abbr>
        </span>
        <textarea
          id="decision-decisionText"
          value={values.decisionText}
          onChange={(event) => set("decisionText", event.target.value)}
          aria-invalid={cardError(t, errors.decisionText) !== null}
        />
        {cardError(t, errors.decisionText) ? (
          <span className="field-error">{cardError(t, errors.decisionText)}</span>
        ) : null}
      </label>
      {mutation.isError ? <MutationError error={mutation.error} /> : null}
      {saved ? (
        <p className="form-success" role="status">
          {t("card.decision.success")}
        </p>
      ) : null}
      <Button type="submit" variant="primary" disabled={mutation.isPending}>
        {mutation.isPending ? t("card.decision.submitting") : t("card.decision.submit")}
      </Button>
    </form>
  );
}

/**
 * Render the close form (closure reason, response date or a recorded reason for its absence).
 *
 * When the appeal is already closed the form is replaced by an "already closed" notice, since the
 * Ticket Service rejects re-closing a terminal appeal.
 *
 * Args:
 *   props: The current card and reference entries.
 *
 * Returns:
 *   The close form element (or the already-closed notice).
 */
export function CloseForm({ card, entries }: CommandFormProps): React.JSX.Element {
  const { t } = useTranslation();
  const [values, setValues] = useState<CloseFormValues>({
    closureReasonCode: card.closureReasonCode ?? "",
    responseSentAt: "",
    noResponseReason: "",
  });
  const [errors, setErrors] = useState<CardErrors>({});
  const mutation = useCloseTicket(card.id);

  if (card.closedAt !== null) {
    return (
      <section className="card-command" aria-label={t("card.close.title")}>
        <h3>{t("card.close.title")}</h3>
        <p role="status">{t("card.close.alreadyClosed")}</p>
      </section>
    );
  }

  const set = <K extends keyof CloseFormValues>(field: K, value: string): void => {
    setValues((prev) => ({ ...prev, [field]: value }));
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const { errors: found, request } = buildCloseRequest(values, card.version);
    setErrors(found);
    if (request === null) {
      return;
    }
    mutation.mutate(request);
  };

  return (
    <form className="card-command" onSubmit={onSubmit} aria-label={t("card.close.title")}>
      <h3>{t("card.close.title")}</h3>
      <ReferenceSelect
        id="close-closureReasonCode"
        label={t("card.field.closureReasonCode")}
        type="closure_reason"
        entries={entries}
        value={values.closureReasonCode}
        required
        error={cardError(t, errors.closureReasonCode)}
        onChange={(value) => set("closureReasonCode", value)}
      />
      <label htmlFor="close-responseSentAt">
        <span>{t("card.field.responseSentAt")}</span>
        <input
          id="close-responseSentAt"
          type="datetime-local"
          value={values.responseSentAt}
          onChange={(event) => set("responseSentAt", event.target.value)}
          aria-invalid={cardError(t, errors.responseSentAt) !== null}
        />
        {cardError(t, errors.responseSentAt) ? (
          <span className="field-error">{cardError(t, errors.responseSentAt)}</span>
        ) : null}
      </label>
      <label htmlFor="close-noResponseReason">
        <span>{t("card.field.noResponseReason")}</span>
        <textarea
          id="close-noResponseReason"
          value={values.noResponseReason}
          onChange={(event) => set("noResponseReason", event.target.value)}
        />
      </label>
      {cardError(t, errors.response) ? (
        <p className="field-error" role="alert">
          {cardError(t, errors.response)}
        </p>
      ) : null}
      {mutation.isError ? <MutationError error={mutation.error} /> : null}
      <Button type="submit" variant="danger" disabled={mutation.isPending}>
        {mutation.isPending ? t("card.close.submitting") : t("card.close.submit")}
      </Button>
    </form>
  );
}

/**
 * Render the legal-hold control (set or clear the hold, with an optional reason).
 *
 * Args:
 *   props: The current card (the button toggles its `legalHold` flag).
 *
 * Returns:
 *   The legal-hold control element.
 */
export function LegalHoldControl({ card }: { card: TicketResponse }): React.JSX.Element {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const mutation = useSetLegalHold(card.id);

  // Setting or clearing a legal hold is a regulatory action (it suspends retention deletion), so it
  // is confirmed in a modal before the mutation is sent rather than firing on the first click.
  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setConfirmOpen(true);
  };

  const confirm = (): void => {
    setConfirmOpen(false);
    mutation.mutate({
      expectedVersion: card.version,
      legalHold: !card.legalHold,
      reason: reason.trim() === "" ? null : reason.trim(),
    });
  };

  const actionLabel = card.legalHold ? t("card.legalHold.clear") : t("card.legalHold.set");

  return (
    <form className="card-command" onSubmit={onSubmit} aria-label={t("card.legalHold.title")}>
      <h3>{t("card.legalHold.title")}</h3>
      <p>{card.legalHold ? t("card.legalHold.on") : t("card.legalHold.off")}</p>
      <label htmlFor="legalHold-reason">
        <span>{t("card.field.legalHoldReason")}</span>
        <input
          id="legalHold-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {mutation.isError ? <MutationError error={mutation.error} /> : null}
      <Button type="submit" variant="primary" disabled={mutation.isPending}>
        {mutation.isPending ? t("card.legalHold.submitting") : actionLabel}
      </Button>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={t("card.legalHold.title")}
        footer={
          <>
            <Button type="button" onClick={() => setConfirmOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="button" variant="primary" onClick={confirm}>
              {actionLabel}
            </Button>
          </>
        }
      >
        <p>{card.legalHold ? t("card.legalHold.confirmClear") : t("card.legalHold.confirmSet")}</p>
      </Dialog>
    </form>
  );
}
