/**
 * Appeal comments section: the comment list and the add-comment form.
 *
 * The list renders the comments read by the workspace aggregation; when that optional section could
 * not be read it shows an "unavailable" notice instead of an empty list (so a partial failure is not
 * mistaken for "no comments"). The add-comment form is rendered only when the caller holds the
 * `ticket:comment` permission (first-line read-only users see the list without it); the gateway and
 * Ticket Service enforce the same claim.
 */
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { CommentResponse } from "../../api/types";
import { formatDateTime } from "../../lib/format";
import { MutationError } from "./MutationError";
import { useAddComment } from "./useTicketCommands";

/** Props for the comments section. */
export interface CommentsSectionProps {
  /** The appeal identifier the comments belong to. */
  ticketId: string;
  /** The comments read from the workspace, or null when the section is unavailable. */
  comments: CommentResponse[] | null;
  /** Whether the optional comments section failed to load (a flagged partial failure). */
  unavailable: boolean;
  /** Whether the caller may add comments (`ticket:comment`). */
  canComment: boolean;
}

/**
 * Render the appeal comments list and, when permitted, the add-comment form.
 *
 * Args:
 *   props: The appeal id, comments, availability flag, and comment permission.
 *
 * Returns:
 *   The comments section element.
 */
export function CommentsSection({
  ticketId,
  comments,
  unavailable,
  canComment,
}: CommentsSectionProps): React.JSX.Element {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "ru";
  const [body, setBody] = useState("");
  const mutation = useAddComment(ticketId);

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (body.trim() === "") {
      return;
    }
    mutation.mutate(
      { body: body.trim() },
      {
        onSuccess: () => {
          setBody("");
        },
      },
    );
  };

  return (
    <section className="card-comments" aria-label={t("card.comments.title")}>
      <h3>{t("card.comments.title")}</h3>

      {unavailable ? (
        <p role="status" className="section-unavailable">
          {t("card.comments.unavailable")}
        </p>
      ) : null}

      {!unavailable && (comments === null || comments.length === 0) ? (
        <p role="status">{t("card.comments.empty")}</p>
      ) : null}

      {comments && comments.length > 0 ? (
        <ul className="card-comments__list">
          {comments.map((comment) => (
            <li key={comment.id} className="card-comment">
              <div className="card-comment__meta">
                <span className="card-comment__author">{comment.authorId}</span>
                <span className="card-comment__time">
                  {formatDateTime(comment.createdAt, locale)}
                </span>
              </div>
              <p className="card-comment__body">{comment.body}</p>
            </li>
          ))}
        </ul>
      ) : null}

      {canComment ? (
        <form className="card-comment-form" onSubmit={onSubmit}>
          <label htmlFor="comment-body">
            <span>{t("card.comments.add")}</span>
            <textarea
              id="comment-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
          </label>
          {mutation.isError ? <MutationError error={mutation.error} /> : null}
          <button type="submit" disabled={mutation.isPending || body.trim() === ""}>
            {mutation.isPending ? t("card.comments.adding") : t("card.comments.submit")}
          </button>
        </form>
      ) : null}
    </section>
  );
}
