/**
 * Manual appeal-registration page.
 *
 * Renders a controlled form for registering any written appeal (DoD 01E-3): required fields are
 * validated client-side before submission and every demographic field is optional. Reference-code
 * selects (intake channel, product, classifier, priority, gender) are populated from the gateway
 * reference-data endpoint. On success the assigned registration number is shown and the appeal list
 * cache is refreshed. Access requires the `ticket:create` permission; the confidential flag is
 * offered only to confidentiality-cleared roles (the gateway enforces the same rule).
 */
import { useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/context";
import { errorCorrelationId, errorMessageKey } from "../../api/errorMessages";
import { Alert, Button } from "../../components/ui";
import type { DataSource, ReferenceEntry, TicketResponse } from "../../api/types";
import {
  EMPTY_REGISTER_VALUES,
  buildCreateRequest,
  type ApplicantFormValues,
  type RegisterErrors,
  type RegisterFormValues,
} from "./registerValues";
import { useCreateTicket } from "./useCreateTicket";
import { useReferenceData } from "./useReferenceData";

/** Roles allowed to mark an appeal confidential (mirrors the gateway/Ticket policy, ADR-0008). */
const CONFIDENTIAL_ROLES = new Set(["SUPERVISOR", "OMBUDSMAN"]);

/** Selectable data-source provenance values (fixed enum, not a reference dictionary). */
const DATA_SOURCES: DataSource[] = ["MANUAL", "APPEAL", "CORE_SYSTEM"];

/**
 * Generate an idempotency key for a registration submission.
 *
 * Returns:
 *   A UUID when the platform provides `crypto.randomUUID`, otherwise a timestamped random string.
 */
function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `reg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Group reference entries by dictionary type, preserving the server's sort order.
 *
 * Args:
 *   entries: The reference entries.
 *
 * Returns:
 *   A map from dictionary type to its entries.
 */
function groupByType(entries: readonly ReferenceEntry[]): Map<string, ReferenceEntry[]> {
  const map = new Map<string, ReferenceEntry[]>();
  for (const entry of entries) {
    const list = map.get(entry.dictionaryType) ?? [];
    list.push(entry);
    map.set(entry.dictionaryType, list);
  }
  return map;
}

/** Props for the party (consumer/representative) sub-form. */
interface PartyFieldsProps {
  /** The party values. */
  values: ApplicantFormValues;
  /** The field-path prefix used for error lookup (`applicant` or `representative`). */
  prefix: "applicant" | "representative";
  /** The current form errors. */
  errors: RegisterErrors;
  /** Whether to show the representative-basis field. */
  showRepresentativeBasis: boolean;
  /** Gender reference options to render. */
  genderOptions: ReferenceEntry[];
  /** Localized label for a reference entry. */
  labelOf: (entry: ReferenceEntry) => string;
  /** Called when a party field changes. */
  onChange: (field: keyof ApplicantFormValues, value: string) => void;
}

/**
 * Render the optional demographic fields for one party.
 *
 * Args:
 *   props: The party values, error map, options, and change handler.
 *
 * Returns:
 *   The party field group.
 */
function PartyFields({
  values,
  prefix,
  errors,
  showRepresentativeBasis,
  genderOptions,
  labelOf,
  onChange,
}: PartyFieldsProps): React.JSX.Element {
  const { t } = useTranslation();
  const ageError = errors[`${prefix}.age`];
  const identifierError = errors[`${prefix}.identifierValue`];
  return (
    <div className="party-fields">
      <label htmlFor={`${prefix}-dataSource`}>
        <span>{t("register.field.dataSource")}</span>
        <select
          id={`${prefix}-dataSource`}
          value={values.dataSource}
          onChange={(event) => onChange("dataSource", event.target.value)}
        >
          {DATA_SOURCES.map((source) => (
            <option key={source} value={source}>
              {t(`register.dataSource.${source}`)}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor={`${prefix}-fullName`}>
        <span>{t("register.field.fullName")}</span>
        <input
          id={`${prefix}-fullName`}
          value={values.fullName}
          onChange={(event) => onChange("fullName", event.target.value)}
        />
      </label>
      <label htmlFor={`${prefix}-identifierType`}>
        <span>{t("register.field.identifierType")}</span>
        <select
          id={`${prefix}-identifierType`}
          value={values.identifierType}
          onChange={(event) => onChange("identifierType", event.target.value)}
        >
          <option value="">{t("register.identifierType.none")}</option>
          <option value="IIN">{t("register.identifierType.IIN")}</option>
          <option value="BIN">{t("register.identifierType.BIN")}</option>
        </select>
      </label>
      <label htmlFor={`${prefix}-identifierValue`}>
        <span>{t("register.field.identifierValue")}</span>
        <input
          id={`${prefix}-identifierValue`}
          value={values.identifierValue}
          onChange={(event) => onChange("identifierValue", event.target.value)}
        />
        {identifierError ? (
          <span className="field-error">{t(`register.error.${identifierError}`)}</span>
        ) : null}
      </label>
      <label htmlFor={`${prefix}-email`}>
        <span>{t("register.field.email")}</span>
        <input
          id={`${prefix}-email`}
          value={values.email}
          onChange={(event) => onChange("email", event.target.value)}
        />
      </label>
      <label htmlFor={`${prefix}-phone`}>
        <span>{t("register.field.phone")}</span>
        <input
          id={`${prefix}-phone`}
          value={values.phone}
          onChange={(event) => onChange("phone", event.target.value)}
        />
      </label>
      <label htmlFor={`${prefix}-genderCode`}>
        <span>{t("register.field.genderCode")}</span>
        <select
          id={`${prefix}-genderCode`}
          value={values.genderCode}
          onChange={(event) => onChange("genderCode", event.target.value)}
        >
          <option value="">{t("register.selectPlaceholder")}</option>
          {genderOptions.map((entry) => (
            <option key={entry.code} value={entry.code}>
              {labelOf(entry)}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor={`${prefix}-birthDate`}>
        <span>{t("register.field.birthDate")}</span>
        <input
          id={`${prefix}-birthDate`}
          type="date"
          value={values.birthDate}
          onChange={(event) => onChange("birthDate", event.target.value)}
        />
      </label>
      <label htmlFor={`${prefix}-age`}>
        <span>{t("register.field.age")}</span>
        <input
          id={`${prefix}-age`}
          inputMode="numeric"
          value={values.age}
          onChange={(event) => onChange("age", event.target.value)}
        />
        {ageError ? <span className="field-error">{t(`register.error.${ageError}`)}</span> : null}
      </label>
      <label htmlFor={`${prefix}-regionCode`}>
        <span>{t("register.field.regionCode")}</span>
        <input
          id={`${prefix}-regionCode`}
          value={values.regionCode}
          onChange={(event) => onChange("regionCode", event.target.value)}
        />
      </label>
      {showRepresentativeBasis ? (
        <label htmlFor={`${prefix}-representativeBasis`}>
          <span>{t("register.field.representativeBasis")}</span>
          <input
            id={`${prefix}-representativeBasis`}
            value={values.representativeBasis}
            onChange={(event) => onChange("representativeBasis", event.target.value)}
          />
        </label>
      ) : null}
    </div>
  );
}

/**
 * Render the manual appeal-registration page.
 *
 * Returns:
 *   The registration page element.
 */
export function RegisterTicketPage(): React.JSX.Element {
  const { t, i18n } = useTranslation();
  const { session, hasPermission } = useAuth();
  const referenceQuery = useReferenceData();
  const mutation = useCreateTicket();

  const [values, setValues] = useState<RegisterFormValues>(EMPTY_REGISTER_VALUES);
  const [errors, setErrors] = useState<RegisterErrors>({});
  const [registered, setRegistered] = useState<TicketResponse | null>(null);
  // A stable key per submission so a retry after a transient failure reconciles instead of
  // duplicating; reset after a successful registration for the next appeal.
  const idempotencyKey = useRef(newIdempotencyKey());

  const entriesByType = useMemo(
    () => groupByType(referenceQuery.data?.entries ?? []),
    [referenceQuery.data],
  );
  const labelOf = useMemo(() => {
    const preferKazakh = i18n.language.startsWith("kk");
    return (entry: ReferenceEntry): string =>
      preferKazakh && entry.displayNameKk ? entry.displayNameKk : entry.displayNameRu;
  }, [i18n.language]);

  if (!hasPermission("ticket:create")) {
    return (
      <section className="register-page">
        <h2>{t("register.title")}</h2>
        <Alert tone="error">{t("register.forbidden")}</Alert>
      </section>
    );
  }

  const canConfidential = (session?.roles ?? []).some((role) => CONFIDENTIAL_ROLES.has(role));
  const referenceOptions = (type: string): ReferenceEntry[] => entriesByType.get(type) ?? [];

  const setTop = <K extends keyof RegisterFormValues>(
    field: K,
    value: RegisterFormValues[K],
  ): void => {
    setValues((prev) => ({ ...prev, [field]: value }));
  };
  const setParty = (
    party: "applicant" | "representative",
    field: keyof ApplicantFormValues,
    value: string,
  ): void => {
    setValues((prev) => ({ ...prev, [party]: { ...prev[party], [field]: value } }));
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const { errors: found, request } = buildCreateRequest(values);
    setErrors(found);
    if (request === null) {
      return;
    }
    mutation.mutate(
      { body: request, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: (ticket) => {
          setRegistered(ticket);
          setValues(EMPTY_REGISTER_VALUES);
          setErrors({});
          idempotencyKey.current = newIdempotencyKey();
        },
      },
    );
  };

  const requiredError = (field: keyof RegisterFormValues): string | null => {
    const code = errors[field];
    return code ? t(`register.error.${code}`) : null;
  };

  const renderReferenceSelect = (
    field: "sourceChannelCode" | "productCode" | "classifierCode" | "priorityCode",
    type: string,
  ): React.JSX.Element => {
    const error = requiredError(field);
    return (
      <label htmlFor={`register-${field}`}>
        <span>
          {t(`register.field.${field}`)} <abbr title={t("register.required")}>*</abbr>
        </span>
        <select
          id={`register-${field}`}
          value={values[field]}
          onChange={(event) => setTop(field, event.target.value)}
          aria-invalid={error !== null}
        >
          <option value="">{t("register.selectPlaceholder")}</option>
          {referenceOptions(type).map((entry) => (
            <option key={entry.code} value={entry.code}>
              {labelOf(entry)}
            </option>
          ))}
        </select>
        {error ? <span className="field-error">{error}</span> : null}
      </label>
    );
  };

  return (
    <section className="register-page">
      <h2>{t("register.title")}</h2>

      {registered ? (
        <Alert tone="success">
          <p>{t("register.success", { number: registered.registrationNumber })}</p>
          <Link to="/tickets">{t("register.backToList")}</Link>
        </Alert>
      ) : null}

      {referenceQuery.isError ? (
        <Alert tone="error">
          <p>{t("register.referenceError")}</p>
          <Button type="button" onClick={() => void referenceQuery.refetch()}>
            {t("common.retry")}
          </Button>
        </Alert>
      ) : null}

      {mutation.isError ? (
        <Alert tone="error">
          <p>{t(errorMessageKey(mutation.error))}</p>
          {errorCorrelationId(mutation.error) ? (
            <p className="error-correlation">
              {t("errors.correlation", { id: errorCorrelationId(mutation.error) })}
            </p>
          ) : null}
        </Alert>
      ) : null}

      <form className="register-form" onSubmit={onSubmit} aria-label={t("register.title")}>
        <fieldset>
          <legend>{t("register.section.main")}</legend>
          <label htmlFor="register-receivedAt">
            <span>
              {t("register.field.receivedAt")} <abbr title={t("register.required")}>*</abbr>
            </span>
            <input
              id="register-receivedAt"
              type="datetime-local"
              value={values.receivedAt}
              onChange={(event) => setTop("receivedAt", event.target.value)}
              aria-invalid={requiredError("receivedAt") !== null}
            />
            {requiredError("receivedAt") ? (
              <span className="field-error">{requiredError("receivedAt")}</span>
            ) : null}
          </label>

          {renderReferenceSelect("sourceChannelCode", "channel")}

          <label htmlFor="register-subject">
            <span>
              {t("register.field.subject")} <abbr title={t("register.required")}>*</abbr>
            </span>
            <input
              id="register-subject"
              value={values.subject}
              onChange={(event) => setTop("subject", event.target.value)}
              aria-invalid={requiredError("subject") !== null}
            />
            {requiredError("subject") ? (
              <span className="field-error">{requiredError("subject")}</span>
            ) : null}
          </label>

          <label htmlFor="register-description">
            <span>
              {t("register.field.description")} <abbr title={t("register.required")}>*</abbr>
            </span>
            <textarea
              id="register-description"
              value={values.description}
              onChange={(event) => setTop("description", event.target.value)}
              aria-invalid={requiredError("description") !== null}
            />
            {requiredError("description") ? (
              <span className="field-error">{requiredError("description")}</span>
            ) : null}
          </label>

          {renderReferenceSelect("productCode", "product")}
          {renderReferenceSelect("classifierCode", "classifier")}
          {renderReferenceSelect("priorityCode", "priority")}

          <label htmlFor="register-contractNumber">
            <span>{t("register.field.contractNumber")}</span>
            <input
              id="register-contractNumber"
              value={values.contractNumber}
              onChange={(event) => setTop("contractNumber", event.target.value)}
            />
          </label>

          {canConfidential ? (
            <label htmlFor="register-isConfidential" className="checkbox">
              <input
                id="register-isConfidential"
                type="checkbox"
                checked={values.isConfidential}
                onChange={(event) => setTop("isConfidential", event.target.checked)}
              />
              <span>{t("register.field.isConfidential")}</span>
            </label>
          ) : null}
        </fieldset>

        <fieldset>
          <legend>{t("register.section.applicant")}</legend>
          <PartyFields
            values={values.applicant}
            prefix="applicant"
            errors={errors}
            showRepresentativeBasis={false}
            genderOptions={referenceOptions("gender")}
            labelOf={labelOf}
            onChange={(field, value) => setParty("applicant", field, value)}
          />
        </fieldset>

        <fieldset>
          <legend>{t("register.section.representative")}</legend>
          <label htmlFor="register-includeRepresentative" className="checkbox">
            <input
              id="register-includeRepresentative"
              type="checkbox"
              checked={values.includeRepresentative}
              onChange={(event) => setTop("includeRepresentative", event.target.checked)}
            />
            <span>{t("register.field.includeRepresentative")}</span>
          </label>
          {values.includeRepresentative ? (
            <PartyFields
              values={values.representative}
              prefix="representative"
              errors={errors}
              showRepresentativeBasis
              genderOptions={referenceOptions("gender")}
              labelOf={labelOf}
              onChange={(field, value) => setParty("representative", field, value)}
            />
          ) : null}
        </fieldset>

        <div className="register-form__actions">
          <Button type="submit" variant="primary" disabled={mutation.isPending}>
            {mutation.isPending ? t("register.submitting") : t("register.submit")}
          </Button>
          <Link to="/tickets">{t("register.cancel")}</Link>
        </div>
      </form>
    </section>
  );
}
