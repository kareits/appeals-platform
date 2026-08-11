/**
 * Appeal-card page: the read-only card, its applicants, comments, and the card commands.
 *
 * Loads the aggregated workspace for one appeal (card + comments) and renders the regulatory card
 * detail read-only, followed by the comments section and the command forms. Access requires the
 * `ticket:read` permission; each command form is shown only when the caller also holds the matching
 * command permission, so a first-line read-only user (holding only `ticket:read`) sees the card and
 * comments without any editing controls. Dictionary codes are shown with their localized business
 * labels from the reference-data endpoint (falling back to the raw code). The workspace card and
 * comment payloads are validated at runtime before rendering; a violation fails closed.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../auth/context";
import { ApiError } from "../../api/errors";
import { Alert, Badge, Button, badgeTone } from "../../components/ui";
import { decodeCommentList, decodeTicketResponse } from "../../api/decoders";
import type {
  ApplicantResponse,
  CommentResponse,
  TicketResponse,
  Workspace,
} from "../../api/types";
import { formatDateTime } from "../../lib/format";
import { CommentsSection } from "./CommentsSection";
import {
  ClassifyForm,
  CloseForm,
  DecisionForm,
  EditDetailsForm,
  LegalHoldControl,
} from "./CardCommands";
import { buildLabelLookup, CARD_DICTIONARIES, type LabelLookup } from "./referenceLabels";
import { useReferenceData } from "./useReferenceData";
import { useWorkspace } from "./useWorkspace";

/** The narrowed, runtime-validated contents of a workspace response. */
interface NarrowedWorkspace {
  /** The validated appeal card, or null when the card payload failed validation. */
  card: TicketResponse | null;
  /** The validated comments, or null when the section is unavailable/invalid. */
  comments: CommentResponse[] | null;
  /** Whether the optional comments section was flagged unavailable. */
  commentsUnavailable: boolean;
  /** Whether the card payload violated the wire contract. */
  cardInvalid: boolean;
}

/**
 * Narrow and validate the raw workspace sections into typed card and comments.
 *
 * The workspace `data` payloads are contract-opaque (`unknown`), so they are validated here with the
 * same decoders used on direct responses; a card decode failure is surfaced (fail closed) while an
 * invalid/optional comments section simply degrades.
 *
 * Args:
 *   workspace: The decoded workspace envelope, or undefined while loading.
 *
 * Returns:
 *   The narrowed card and comments with their availability/validity flags.
 */
function narrowWorkspace(workspace: Workspace | undefined): NarrowedWorkspace {
  if (!workspace) {
    return { card: null, comments: null, commentsUnavailable: false, cardInvalid: false };
  }
  const { ticket, comments } = workspace.sections;
  let card: TicketResponse | null = null;
  let cardInvalid = false;
  if (ticket.status === "ok") {
    try {
      card = decodeTicketResponse(ticket.data);
    } catch {
      cardInvalid = true;
    }
  }
  let commentList: CommentResponse[] | null = null;
  if (comments.status === "ok") {
    try {
      commentList = decodeCommentList(comments.data);
    } catch {
      commentList = null;
    }
  }
  return {
    card,
    comments: commentList,
    commentsUnavailable: comments.status === "unavailable",
    cardInvalid,
  };
}

/** Props for a single labelled card field. */
interface CardFieldProps {
  /** The already-localized field label. */
  label: string;
  /** The field value; the field is omitted when null/empty. */
  value: string | null | undefined;
}

/**
 * Render a labelled card field, or nothing when the value is empty.
 *
 * Args:
 *   props: The field label and value.
 *
 * Returns:
 *   The field row, or null when there is no value.
 */
function CardField({ label, value }: CardFieldProps): React.JSX.Element | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return (
    <div className="card-field">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** Props for the applicants list. */
interface ApplicantsListProps {
  /** The parties attached to the appeal. */
  applicants: ApplicantResponse[];
  /** The localized-label lookup for dictionary codes (gender). */
  labels: LabelLookup;
}

/**
 * Render the appeal's parties (consumer and any representative).
 *
 * Args:
 *   props: The applicants and the label lookup.
 *
 * Returns:
 *   The applicants section element.
 */
function ApplicantsList({ applicants, labels }: ApplicantsListProps): React.JSX.Element {
  const { t } = useTranslation();
  return (
    <section className="card-applicants" aria-label={t("card.section.applicants")}>
      <h3>{t("card.section.applicants")}</h3>
      {applicants.map((applicant) => (
        <dl key={applicant.id} className="card-fields">
          <CardField
            label={t("card.field.applicantType")}
            value={t(`card.applicantType.${applicant.applicantType}`)}
          />
          <CardField label={t("card.field.fullName")} value={applicant.fullName} />
          <CardField label={t("card.field.identifierValue")} value={applicant.identifierMasked} />
          <CardField label={t("card.field.email")} value={applicant.email} />
          <CardField label={t("card.field.phone")} value={applicant.phone} />
          <CardField
            label={t("card.field.genderCode")}
            value={labels("gender", applicant.genderCode)}
          />
          <CardField label={t("card.field.regionCode")} value={applicant.regionCode} />
          <CardField
            label={t("card.field.representativeBasis")}
            value={applicant.representativeBasis}
          />
        </dl>
      ))}
    </section>
  );
}

/** Props for the read-only card detail block. */
interface CardDetailsProps {
  /** The appeal card. */
  card: TicketResponse;
  /** The localized-label lookup for dictionary codes. */
  labels: LabelLookup;
  /** The active UI locale for timestamp formatting. */
  locale: string;
}

/**
 * Render the read-only regulatory detail of the appeal card.
 *
 * Args:
 *   props: The card, label lookup, and locale.
 *
 * Returns:
 *   The card detail element.
 */
function CardDetails({ card, labels, locale }: CardDetailsProps): React.JSX.Element {
  const { t } = useTranslation();
  return (
    <section className="card-details" aria-label={t("card.section.details")}>
      <dl className="card-fields">
        <div className="card-field">
          <dt>{t("card.field.status")}</dt>
          <dd>
            <Badge tone={badgeTone("status", card.currentStatusCode)}>
              {labels("status", card.currentStatusCode)}
            </Badge>
          </dd>
        </div>
        <CardField label={t("card.field.stage")} value={labels("stage", card.currentStageCode)} />
        <CardField
          label={t("card.field.sourceChannelCode")}
          value={labels("channel", card.sourceChannelCode)}
        />
        <CardField
          label={t("card.field.productCode")}
          value={labels("product", card.productCode)}
        />
        <CardField
          label={t("card.field.classifierCode")}
          value={labels("classifier", card.classifierCode)}
        />
        <div className="card-field">
          <dt>{t("card.field.priorityCode")}</dt>
          <dd>
            <Badge tone={badgeTone("priority", card.priorityCode)}>
              {labels("priority", card.priorityCode)}
            </Badge>
          </dd>
        </div>
        <CardField label={t("card.field.contractNumber")} value={card.contractNumber} />
        <CardField
          label={t("card.field.receivedAt")}
          value={formatDateTime(card.receivedAt, locale)}
        />
        <CardField
          label={t("card.field.registeredAt")}
          value={formatDateTime(card.registeredAt, locale)}
        />
        <CardField
          label={t("card.field.internalDueAt")}
          value={card.internalDueAt ? formatDateTime(card.internalDueAt, locale) : null}
        />
        <CardField
          label={t("card.field.legalDueAt")}
          value={card.legalDueAt ? formatDateTime(card.legalDueAt, locale) : null}
        />
        <CardField
          label={t("card.field.isConfidential")}
          value={card.isConfidential ? t("card.flag.yes") : t("card.flag.no")}
        />
        <CardField
          label={t("card.field.legalHold")}
          value={card.legalHold ? t("card.flag.yes") : t("card.flag.no")}
        />
      </dl>

      <h3>{t("card.field.description")}</h3>
      <p className="card-description">{card.description}</p>

      {card.decisionCode ? (
        <div className="card-decision">
          <h3>{t("card.section.decision")}</h3>
          <dl className="card-fields">
            <CardField
              label={t("card.field.decisionCode")}
              value={labels("decision", card.decisionCode)}
            />
            <CardField label={t("card.field.decisionSummary")} value={card.decisionSummary} />
            <CardField label={t("card.field.decisionText")} value={card.decisionText} />
            <CardField
              label={t("card.field.decisionAt")}
              value={card.decisionAt ? formatDateTime(card.decisionAt, locale) : null}
            />
          </dl>
        </div>
      ) : null}

      {card.closedAt ? (
        <div className="card-closure">
          <h3>{t("card.section.closure")}</h3>
          <dl className="card-fields">
            <CardField
              label={t("card.field.closureReasonCode")}
              value={labels("closure_reason", card.closureReasonCode)}
            />
            <CardField
              label={t("card.field.closedAt")}
              value={formatDateTime(card.closedAt, locale)}
            />
            <CardField
              label={t("card.field.responseSentAt")}
              value={card.responseSentAt ? formatDateTime(card.responseSentAt, locale) : null}
            />
            <CardField label={t("card.field.noResponseReason")} value={card.noResponseReason} />
            <CardField label={t("card.field.retentionUntil")} value={card.retentionUntil} />
          </dl>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Render the appeal-card page for the routed appeal id.
 *
 * Returns:
 *   The card page element.
 */
export function TicketCardPage(): React.JSX.Element {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "ru";
  const { ticketId = "" } = useParams<{ ticketId: string }>();
  const { hasPermission } = useAuth();

  const workspaceQuery = useWorkspace(ticketId);
  const referenceQuery = useReferenceData(CARD_DICTIONARIES);

  const narrowed = useMemo(() => narrowWorkspace(workspaceQuery.data), [workspaceQuery.data]);
  const labels = useMemo(
    () => buildLabelLookup(referenceQuery.data?.entries ?? [], i18n.language),
    [referenceQuery.data, i18n.language],
  );

  if (!hasPermission("ticket:read")) {
    return (
      <section className="card-page">
        <Alert tone="error">{t("card.forbidden")}</Alert>
        <Link to="/tickets">{t("card.backToList")}</Link>
      </section>
    );
  }

  if (workspaceQuery.isLoading) {
    return (
      <section className="card-page">
        <p role="status">{t("card.loading")}</p>
      </section>
    );
  }

  if (workspaceQuery.isError) {
    const error = workspaceQuery.error;
    const notFound = error instanceof ApiError && error.status === 404;
    const forbidden = error instanceof ApiError && error.status === 403;
    let message = t("card.error.load");
    if (notFound) {
      message = t("card.error.notFound");
    } else if (forbidden) {
      message = t("card.forbidden");
    }
    return (
      <section className="card-page">
        <Alert tone="error">
          <p>{message}</p>
          {!notFound && !forbidden ? (
            <Button type="button" onClick={() => void workspaceQuery.refetch()}>
              {t("common.retry")}
            </Button>
          ) : null}
        </Alert>
        <Link to="/tickets">{t("card.backToList")}</Link>
      </section>
    );
  }

  const { card, comments, commentsUnavailable, cardInvalid } = narrowed;

  if (cardInvalid || card === null) {
    return (
      <section className="card-page">
        <Alert tone="error">{t("card.error.invalid")}</Alert>
        <Link to="/tickets">{t("card.backToList")}</Link>
      </section>
    );
  }

  return (
    <section className="card-page">
      <div className="card-page__header">
        <Link to="/tickets">{t("card.backToList")}</Link>
        <h2>{t("card.title", { number: card.registrationNumber })}</h2>
        <p className="card-subject">{card.subject}</p>
      </div>

      {referenceQuery.isError ? (
        <p className="section-unavailable" role="status">
          {t("card.referenceError")}
        </p>
      ) : null}

      <CardDetails card={card} labels={labels} locale={locale} />

      <ApplicantsList applicants={card.applicants} labels={labels} />

      <CommentsSection
        ticketId={card.id}
        comments={comments}
        unavailable={commentsUnavailable}
        canComment={hasPermission("ticket:comment")}
      />

      {/* Keyed by the card version so a successful card mutation resets the command forms to the
          refreshed card state (new version, cleared inputs). */}
      <div className="card-commands" key={card.version}>
        {hasPermission("ticket:update") ? (
          <EditDetailsForm card={card} entries={referenceQuery.data?.entries ?? []} />
        ) : null}
        {hasPermission("ticket:classify") ? (
          <ClassifyForm card={card} entries={referenceQuery.data?.entries ?? []} />
        ) : null}
        {hasPermission("ticket:decide") ? (
          <DecisionForm card={card} entries={referenceQuery.data?.entries ?? []} />
        ) : null}
        {hasPermission("ticket:close") ? (
          <CloseForm card={card} entries={referenceQuery.data?.entries ?? []} />
        ) : null}
        {hasPermission("ticket:legal_hold") ? <LegalHoldControl card={card} /> : null}
      </div>
    </section>
  );
}
