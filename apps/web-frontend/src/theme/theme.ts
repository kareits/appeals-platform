/**
 * Theme selection (light / dark / follow system).
 *
 * The design system is theme-aware through CSS custom properties: the default follows the OS color
 * scheme via `prefers-color-scheme`, and an explicit choice is expressed by a `data-theme`
 * attribute on the document element that overrides the media query in both directions (see
 * `styles/tokens.css`). This module is the small imperative layer that reads/writes the stored
 * preference and reflects it onto the document; the visual result is entirely token-driven.
 *
 * The preference is a non-sensitive UI setting, so it is kept in `localStorage` (persisting across
 * tabs and sessions), unlike the bearer token which stays in `sessionStorage` (ADR-0009).
 */

/** A user's theme choice: follow the OS ("system") or force light/dark. */
export type ThemeChoice = "system" | "light" | "dark";

/** The valid theme choices, in the order the toggle presents them. */
export const THEME_CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

/** localStorage key holding the persisted theme choice. */
const STORAGE_KEY = "mfo.ui.theme";

/**
 * Read the persisted theme choice.
 *
 * Returns:
 *   The stored choice, or "system" when nothing valid is stored (or storage is unavailable).
 */
export function readStoredTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark" || value === "system") {
      return value;
    }
  } catch {
    // Ignore storage access errors (e.g. disabled storage) and fall back to the system default.
  }
  return "system";
}

/**
 * Reflect a theme choice onto the document element.
 *
 * Sets `data-theme` to force light/dark, or removes it for "system" so `prefers-color-scheme`
 * decides. Setting an attribute (not an inline style) keeps the app within the strict CSP that
 * forbids inline styles (ADR-0009).
 *
 * Args:
 *   choice: The theme choice to apply.
 */
export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", choice);
  }
}

/**
 * Persist a theme choice, ignoring storage errors.
 *
 * Args:
 *   choice: The theme choice to store.
 */
export function storeTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Ignore storage access errors; the choice still applies for the current page.
  }
}

/**
 * Initialize the theme from the stored preference and apply it to the document.
 *
 * Called once at startup (before first paint of the app) so a forced light/dark choice is honored
 * immediately.
 *
 * Returns:
 *   The applied theme choice.
 */
export function initTheme(): ThemeChoice {
  const choice = readStoredTheme();
  applyTheme(choice);
  return choice;
}
