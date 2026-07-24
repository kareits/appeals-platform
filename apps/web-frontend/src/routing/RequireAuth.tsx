/**
 * Route guard that requires an authenticated session.
 *
 * Renders its children only when a session is present; otherwise it redirects to the login page,
 * preserving the attempted location so the user returns there after signing in.
 */
import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth/context";

/**
 * Guard a subtree behind authentication.
 *
 * Args:
 *   children: The protected content to render when authenticated.
 *
 * Returns:
 *   The children when authenticated, otherwise a redirect to `/login`.
 */
export function RequireAuth({ children }: { children: ReactNode }): React.JSX.Element {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
