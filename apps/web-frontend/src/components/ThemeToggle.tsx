/**
 * Theme switcher between following the system scheme and forcing light or dark.
 *
 * A labelled `<select>` bound to the persisted theme choice; changing it applies the choice to the
 * document immediately (see `theme/theme.ts`). The option labels live in the localization layer
 * (ADR-015). Kept as a native select for full keyboard and screen-reader support with no custom
 * widget code.
 */
import { useTranslation } from "react-i18next";
import { THEME_CHOICES } from "../theme/theme";
import { useTheme } from "../theme/useTheme";

/**
 * Render the theme selector bound to the active theme choice.
 *
 * Returns:
 *   A labelled `<select>` for choosing the theme.
 */
export function ThemeToggle(): React.JSX.Element {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  return (
    <label className="theme-toggle">
      <span>{t("app.theme.label")}</span>
      <select
        value={theme}
        onChange={(event) => setTheme(event.target.value as (typeof THEME_CHOICES)[number])}
        aria-label={t("app.theme.label")}
      >
        {THEME_CHOICES.map((choice) => (
          <option key={choice} value={choice}>
            {t(`app.theme.${choice}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
