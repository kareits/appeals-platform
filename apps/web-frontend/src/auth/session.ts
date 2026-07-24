/**
 * Client-side session model and persistence for the dev/local auth scheme.
 *
 * The session holds the bearer token and the claims the gateway resolved at login (subject,
 * username, roles, permissions). It is persisted in `sessionStorage` so a page reload within the
 * same tab keeps the user signed in; closing the tab clears it. This is deliberately lightweight
 * for the temporary dev scheme (docs/06) and carries no long-lived secret beyond the short-lived
 * access token.
 */
import { isUuid, SUPPORTED_ROLES } from "../api/decoders";
import type { TokenResponse } from "../api/types";

/** Storage key for the persisted session. */
const STORAGE_KEY = "mfo.auth.session";

/** The authenticated caller's session as held by the SPA. */
export interface Session {
  accessToken: string;
  subject: string;
  username: string;
  roles: string[];
  permissions: string[];
}

/**
 * Build a session from a successful login response.
 *
 * Args:
 *   token: The gateway's token response.
 *
 * Returns:
 *   The session projected from the token claims.
 */
export function sessionFromToken(token: TokenResponse): Session {
  return {
    accessToken: token.accessToken,
    subject: token.subject,
    username: token.username,
    roles: token.roles,
    permissions: token.permissions,
  };
}

/**
 * Whether every element of an unknown value is a string.
 *
 * Args:
 *   value: The value to check.
 *
 * Returns:
 *   True when the value is an array whose elements are all strings.
 */
function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * Whether every element of a string array is a supported role.
 *
 * Args:
 *   roles: The roles to check.
 *
 * Returns:
 *   True when all roles belong to the supported set.
 */
function areSupportedRoles(roles: string[]): boolean {
  return roles.every((role) => (SUPPORTED_ROLES as readonly string[]).includes(role));
}

/**
 * Load and fully validate the persisted session from `sessionStorage`.
 *
 * Every field is validated (fail closed): a corrupted or partial stored value is discarded rather
 * than treated as an authenticated session. The subject is validated as a UUID with the same
 * validator used for API responses, and restored roles must belong to the supported role set — an
 * invalid subject or unknown role (for example, a tampered `sessionStorage` value) discards the
 * session.
 *
 * Returns:
 *   The stored session, or null when none is present or the stored value is malformed.
 */
export function loadSession(): Session | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }
    const candidate = parsed as Record<string, unknown>;
    if (
      typeof candidate.accessToken !== "string" ||
      candidate.accessToken === "" ||
      typeof candidate.subject !== "string" ||
      !isUuid(candidate.subject) ||
      typeof candidate.username !== "string" ||
      !isStringArray(candidate.roles) ||
      !areSupportedRoles(candidate.roles) ||
      !isStringArray(candidate.permissions)
    ) {
      return null;
    }
    return {
      accessToken: candidate.accessToken,
      subject: candidate.subject,
      username: candidate.username,
      roles: candidate.roles,
      permissions: candidate.permissions,
    };
  } catch {
    return null;
  }
}

/**
 * Persist the session to `sessionStorage`.
 *
 * Args:
 *   session: The session to store.
 */
export function saveSession(session: Session): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

/** Remove any persisted session from `sessionStorage`. */
export function clearSession(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}
