/**
 * Dev/local login page.
 *
 * Collects username and password and authenticates through the gateway (`POST /api/v1/auth/login`)
 * via the auth context. On success it navigates to the originally requested page (or the appeal
 * list); failures are mapped to localized messages by HTTP status. This is the temporary dev/local
 * scheme (docs/06); corporate OIDC replaces it later.
 */
import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/context";
import { ApiError } from "../../api/errors";
import { errorMessageKey } from "../../api/errorMessages";

/** Router location state carrying the page the user was redirected from. */
interface FromState {
  from?: { pathname?: string };
}

/**
 * Map a login failure to a localized message key.
 *
 * 401 and 403 carry login-specific copy (bad credentials vs dev-auth disabled); other failures
 * (network, timeout, invalid response, 5xx) fall back to the shared transport-error mapping.
 *
 * Args:
 *   error: The error thrown by the login request.
 *
 * Returns:
 *   The i18n key describing the failure.
 */
function loginErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "login.error.invalid";
    }
    if (error.status === 403) {
      return "login.error.disabled";
    }
  }
  return errorMessageKey(error);
}

/**
 * Render the login form.
 *
 * Returns:
 *   The login page element.
 */
export function LoginPage(): React.JSX.Element {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: () => login({ username, password }),
    onSuccess: () => {
      const state = location.state as FromState | null;
      const target = state?.from?.pathname ?? "/tickets";
      navigate(target, { replace: true });
    },
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <div className="login-page">
      <form className="login-form" onSubmit={onSubmit} aria-labelledby="login-title">
        <h1 id="login-title">{t("login.title")}</h1>

        <label htmlFor="login-username">{t("login.username")}</label>
        <input
          id="login-username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />

        <label htmlFor="login-password">{t("login.password")}</label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />

        {mutation.isError ? (
          <p className="form-error" role="alert">
            {t(loginErrorKey(mutation.error))}
          </p>
        ) : null}

        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? t("login.submitting") : t("login.submit")}
        </button>
      </form>
    </div>
  );
}
