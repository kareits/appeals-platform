/**
 * Authentication provider: session state, login/logout, and the gateway API client.
 *
 * The provider owns the current session, exposes `login`/`logout`, derives a `hasPermission`
 * helper from the resolved permission claims, and builds a single `ApiClient` bound to the live
 * token. A `401` from any request triggers `logout` so the UI falls back to the login screen. The
 * context object and the `useAuth` hook live in `./context` so this module exports only a component.
 */
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "../api/client";
import { login as loginRequest } from "../api/auth";
import type { LoginRequest } from "../api/types";
import { clearSession, loadSession, saveSession, sessionFromToken, type Session } from "./session";
import { AuthContext, type AuthContextValue } from "./context";

/**
 * Provide authentication state and the gateway client to the tree.
 *
 * Args:
 *   children: The subtree that consumes the auth context.
 */
export function AuthProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const queryClient = useQueryClient();

  // The client reads the token through a ref so a single client instance always sees the latest
  // session without being rebuilt (which would reset in-flight React Query caches).
  const sessionRef = useRef<Session | null>(session);
  sessionRef.current = session;

  // Ending a session must not leave another user's ticket data in the shared query cache. Cancel
  // in-flight protected queries (which aborts their fetches) and remove all cached results, so a
  // later login in the same tab cannot render the previous user's rows (CR-WEB-HIGH-001).
  const clearAuthState = useCallback(() => {
    clearSession();
    setSession(null);
    void queryClient.cancelQueries();
    queryClient.clear();
  }, [queryClient]);

  const logout = useCallback(() => {
    clearAuthState();
  }, [clearAuthState]);

  const client = useMemo(
    () =>
      createApiClient({
        getToken: () => sessionRef.current?.accessToken ?? null,
        onUnauthorized: clearAuthState,
      }),
    [clearAuthState],
  );

  const login = useCallback(
    async (credentials: LoginRequest) => {
      // Drop any residual cache before establishing a new identity (defence in depth alongside
      // subject-scoped query keys).
      queryClient.clear();
      const token = await loginRequest(client, credentials);
      const next = sessionFromToken(token);
      saveSession(next);
      setSession(next);
    },
    [client, queryClient],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: session !== null,
      client,
      login,
      logout,
      hasPermission: (permission: string) => session?.permissions.includes(permission) ?? false,
    }),
    [session, client, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
