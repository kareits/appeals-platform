/**
 * Localized reference-dictionary label lookup for the appeal card.
 *
 * The card stores stable dictionary codes (status, stage, product, decision, and so on); the UI
 * shows their business display names from the reference-data endpoint. This module builds a lookup
 * that resolves a `(dictionaryType, code)` pair to its localized label, preferring the Kazakh name
 * when the active language is Kazakh and it is defined, and falling back to the raw code when the
 * dictionary has no matching active entry (so an unknown code is still shown, never hidden).
 */
import type { ReferenceEntry } from "../../api/types";

/** Dictionaries the appeal card and its command forms need for labels and select options. */
export const CARD_DICTIONARIES = [
  "channel",
  "product",
  "classifier",
  "priority",
  "status",
  "stage",
  "decision",
  "closure_reason",
  "gender",
] as const;

/** A function resolving a dictionary code to its localized label (falls back to the code). */
export type LabelLookup = (dictionaryType: string, code: string | null | undefined) => string;

/**
 * Localized display name for a single reference entry.
 *
 * Args:
 *   entry: The reference entry.
 *   preferKazakh: Whether to prefer the Kazakh label when defined.
 *
 * Returns:
 *   The Kazakh label when preferred and present, otherwise the Russian label.
 */
export function entryLabel(entry: ReferenceEntry, preferKazakh: boolean): string {
  return preferKazakh && entry.displayNameKk ? entry.displayNameKk : entry.displayNameRu;
}

/**
 * Build a `(type, code)` label lookup from reference entries for the active language.
 *
 * Args:
 *   entries: The active reference entries.
 *   language: The active i18n language code (for example, "ru" or "kk").
 *
 * Returns:
 *   A lookup returning the localized label, or the raw code when no active entry matches (an empty
 *   or missing code yields an empty string).
 */
export function buildLabelLookup(
  entries: readonly ReferenceEntry[],
  language: string,
): LabelLookup {
  const preferKazakh = language.startsWith("kk");
  const byKey = new Map<string, ReferenceEntry>();
  for (const entry of entries) {
    byKey.set(`${entry.dictionaryType}:${entry.code}`, entry);
  }
  return (dictionaryType, code) => {
    if (!code) {
      return "";
    }
    const entry = byKey.get(`${dictionaryType}:${code}`);
    return entry ? entryLabel(entry, preferKazakh) : code;
  };
}

/**
 * Reference options of one dictionary type, in the server's sort order.
 *
 * Args:
 *   entries: The active reference entries.
 *   dictionaryType: The dictionary to filter to.
 *
 * Returns:
 *   The entries of the given type (already ordered by the server).
 */
export function optionsOfType(
  entries: readonly ReferenceEntry[],
  dictionaryType: string,
): ReferenceEntry[] {
  return entries.filter((entry) => entry.dictionaryType === dictionaryType);
}
