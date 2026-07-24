/**
 * Internationalization setup (react-i18next).
 *
 * Registers the Russian and Kazakh UI dictionaries and configures language detection. All
 * user-facing copy lives in the locale JSON files (the localization/business-content layer,
 * ADR-015); technical code never hard-codes Russian or Kazakh strings. Russian is the default and
 * fallback language.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import ru from "./locales/ru.json";
import kk from "./locales/kk.json";

/** The languages the UI ships translations for. */
export const SUPPORTED_LANGUAGES = ["ru", "kk"] as const;

/** A supported UI language code. */
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      kk: { translation: kk },
    },
    fallbackLng: "ru",
    supportedLngs: SUPPORTED_LANGUAGES,
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  });

export default i18n;
