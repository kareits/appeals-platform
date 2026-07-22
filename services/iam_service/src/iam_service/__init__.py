"""IAM Service: users, roles, teams, and the authorization matrix.

Owns identity data and issues permission claims (a signed JWT) that downstream services verify
independently (ADR-007 forbids a shared permission-rule library). Dev/local authentication is
available outside production only (docs/06).
"""
