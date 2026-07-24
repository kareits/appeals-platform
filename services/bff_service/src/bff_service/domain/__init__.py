"""BFF domain layer.

The gateway owns no business domain. This package holds only the small set of authorization
constants the gateway enforces — the permission claim strings it checks on the resolved auth
context. The strings are defined independently here (not imported from the IAM service): ADR-007
forbids a shared permission package, and ADR-004 forbids importing another service's code.
"""
