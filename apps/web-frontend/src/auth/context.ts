/**
 * Auth context object, its value type, and the `useAuth` hook.
 *
 * Kept separate from the `AuthProvider` component so the provider module exports only a component
 * (React Fast Refresh requires component-only modules). `AuthProvider` in `AuthContext.tsx`
 * populates this context; consumers read it through `useAuth`.
 */
import { createContext, useContext } from "react";
import type { ApiClient } from "../api/client";
import type { LoginRequest } from "../api/types";
import type { Session } from "./session";

/** The value exposed by the auth context. */
export interface AuthContextValue {
  /** The current session, or null when signed out. */
  session: Session | null;
  /** Whether a session is present. */
  isAuthenticated: boolean;
  /** The gateway client bound to the current token. */
  client: ApiClient;
  /** Authenticate and establish a session. */
  login: (credentials: LoginRequest) => Promise<void>;
  /** Clear the session and persisted state. */
  logout: () => void;
  /** Whether the current session holds the given permission claim. */
  hasPermission: (permission: string) => boolean;
}

/** The React context carrying the auth value; null until an `AuthProvider` is mounted. */
export const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Access the auth context.
 *
 * Returns:
 *   The current auth context value.
 *
 * Raises:
 *   Error: When used outside an `AuthProvider`.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
