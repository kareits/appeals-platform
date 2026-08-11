/**
 * Application shell for authenticated pages.
 *
 * Renders the product header (title, signed-in user, language switcher, and logout) around the
 * routed page content. Logging out clears the session and returns to the login screen.
 */
import { useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/context";
import { Button } from "./ui";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";

/**
 * Wrap authenticated page content with the product header.
 *
 * Args:
 *   children: The page content to render inside the shell.
 */
export function AppLayout({ children }: { children: ReactNode }): React.JSX.Element {
  const { t } = useTranslation();
  const { session, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1 className="app-title">{t("app.title")}</h1>
        <div className="app-header__actions">
          <ThemeToggle />
          <LanguageSwitcher />
          {session ? (
            <span className="app-user">{t("nav.signedInAs", { username: session.username })}</span>
          ) : null}
          <Button
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
          >
            {t("nav.logout")}
          </Button>
        </div>
      </header>
      <main className="app-content">{children}</main>
    </div>
  );
}
