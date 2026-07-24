/**
 * Language switcher between the supported UI languages (Russian and Kazakh).
 *
 * Changing the selection updates the active i18next language, which react-i18next persists via the
 * configured detector cache.
 */
import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES } from "../i18n";

/**
 * Render a language selector bound to the active i18next language.
 *
 * Returns:
 *   A labeled `<select>` for choosing the UI language.
 */
export function LanguageSwitcher(): React.JSX.Element {
  const { i18n, t } = useTranslation();
  const current = i18n.resolvedLanguage ?? "ru";

  return (
    <label className="language-switcher">
      <span>{t("app.language")}</span>
      <select
        value={current}
        onChange={(event) => {
          void i18n.changeLanguage(event.target.value);
        }}
        aria-label={t("app.language")}
      >
        {SUPPORTED_LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>
            {t(`app.lang.${lang}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
