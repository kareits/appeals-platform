/**
 * Authentication endpoint wrappers over the BFF gateway.
 *
 * These functions call the gateway's dev/local login and auth-context endpoints and validate the
 * responses at runtime (never trusting `as T`). The dev/local scheme is temporary (docs/06); the
 * wire shape stays compatible with the corporate OIDC that replaces it later.
 */
import type { ApiClient } from "./client";
import { decodeAuthContext, decodeTokenResponse } from "./decoders";
import type { AuthContext, LoginRequest, TokenResponse } from "./types";

/**
 * Authenticate with username and password.
 *
 * Args:
 *   client: The gateway client.
 *   credentials: The login handle and password.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The validated signed access token and resolved claims.
 *
 * Raises:
 *   ApiError: 401 for bad credentials, 403 when dev auth is disabled.
 *   ProtocolError: When the response body fails validation.
 */
export function login(
  client: ApiClient,
  credentials: LoginRequest,
  signal?: AbortSignal,
): Promise<TokenResponse> {
  return client.request<TokenResponse>("/auth/login", {
    method: "POST",
    body: credentials,
    signal,
    decode: decodeTokenResponse,
  });
}

/**
 * Resolve the current caller's auth context from the bearer token.
 *
 * Args:
 *   client: The gateway client.
 *   signal: Optional cancellation signal.
 *
 * Returns:
 *   The validated subject, username, roles, and permissions.
 *
 * Raises:
 *   ApiError: 401 when the token is missing or rejected.
 *   ProtocolError: When the response body fails validation.
 */
export function getAuthContext(client: ApiClient, signal?: AbortSignal): Promise<AuthContext> {
  return client.request<AuthContext>("/auth/me", { signal, decode: decodeAuthContext });
}
