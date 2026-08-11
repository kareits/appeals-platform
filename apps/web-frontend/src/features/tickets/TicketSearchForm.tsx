/**
 * Appeal search/filter form.
 *
 * A controlled form over the gateway search filters. It keeps its own draft state and lifts the
 * applied values to the parent on submit; a reset clears the draft and applies an empty filter set.
 * Field labels come from the localization layer.
 */
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button, Field, Input } from "../../components/ui";
import { EMPTY_FORM_VALUES, type TicketSearchFormValues } from "./searchValues";

/** Text filter fields rendered as plain text inputs, in display order. */
const TEXT_FIELDS: Array<keyof TicketSearchFormValues> = [
  "registrationNumber",
  "fullName",
  "identifierValue",
  "contractNumber",
  "statusCode",
  "stageCode",
  "productCode",
  "classifierCode",
  "channelCode",
];

/** Date-range filter fields rendered as date inputs, in display order. */
const DATE_FIELDS: Array<keyof TicketSearchFormValues> = [
  "receivedFrom",
  "receivedTo",
  "registeredFrom",
  "registeredTo",
];

/** Props for the search form. */
export interface TicketSearchFormProps {
  /** Initial draft values (defaults to empty). */
  initialValues?: TicketSearchFormValues;
  /** Called with the applied values when the form is submitted or reset. */
  onApply: (values: TicketSearchFormValues) => void;
}

/**
 * Render the appeal search form.
 *
 * Args:
 *   props: Initial values and the apply callback.
 *
 * Returns:
 *   The search form element.
 */
export function TicketSearchForm({
  initialValues = EMPTY_FORM_VALUES,
  onApply,
}: TicketSearchFormProps): React.JSX.Element {
  const { t } = useTranslation();
  const [values, setValues] = useState<TicketSearchFormValues>(initialValues);

  const update = (field: keyof TicketSearchFormValues, value: string): void => {
    setValues((prev) => ({ ...prev, [field]: value }));
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    onApply(values);
  };

  const onReset = (): void => {
    setValues(EMPTY_FORM_VALUES);
    onApply(EMPTY_FORM_VALUES);
  };

  return (
    <form className="ticket-search" onSubmit={onSubmit} aria-label={t("tickets.search.legend")}>
      <fieldset>
        <legend>{t("tickets.search.legend")}</legend>
        <div className="ticket-search__grid">
          {TEXT_FIELDS.map((field) => (
            <Field key={field} id={`filter-${field}`} label={t(`tickets.search.${field}`)}>
              <Input
                name={field}
                value={values[field]}
                onChange={(event) => update(field, event.target.value)}
              />
            </Field>
          ))}
          {DATE_FIELDS.map((field) => (
            <Field key={field} id={`filter-${field}`} label={t(`tickets.search.${field}`)}>
              <Input
                name={field}
                type="date"
                value={values[field]}
                onChange={(event) => update(field, event.target.value)}
              />
            </Field>
          ))}
        </div>
        <div className="ticket-search__actions">
          <Button type="submit" variant="primary">
            {t("tickets.search.submit")}
          </Button>
          <Button type="button" onClick={onReset}>
            {t("tickets.search.reset")}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
