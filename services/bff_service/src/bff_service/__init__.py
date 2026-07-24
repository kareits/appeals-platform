"""BFF service package.

The Backend-for-Frontend is the single API gateway the web frontend talks to. It establishes the
caller's auth context from the IAM service, enforces permission claims at the gateway, aggregates
the appeal workspace from downstream services, and normalizes errors as RFC 7807 Problem Details. It
owns no domain data and duplicates no business logic (BFF_SERVICE spec; TASK_01E-1).
"""
