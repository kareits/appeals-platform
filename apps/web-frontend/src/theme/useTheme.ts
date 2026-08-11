/**
 * React hook for reading and changing the active theme choice.
 *
 * Exposes the current choice and a setter that persists it and reflects it onto the document. The
 * initial state is read from storage so the hook and the document stay in sync after a reload.
 */
import { useCallback, useState } from "react";
import { applyTheme, readStoredTheme, storeTheme, type ThemeChoice } from "./theme";

/** The current theme choice and a setter that persists and applies it. */
export interface UseThemeResult {
  /** The active theme choice. */
  theme: ThemeChoice;
  /** Set, persist, and apply a new theme choice. */
  setTheme: (choice: ThemeChoice) => void;
}

/**
 * Manage the active theme choice.
 *
 * Returns:
 *   The current choice and a setter that persists it to storage and applies it to the document.
 */
export function useTheme(): UseThemeResult {
  const [theme, setThemeState] = useState<ThemeChoice>(() => readStoredTheme());

  const setTheme = useCallback((choice: ThemeChoice): void => {
    setThemeState(choice);
    storeTheme(choice);
    applyTheme(choice);
  }, []);

  return { theme, setTheme };
}
