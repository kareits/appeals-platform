# services

Backend services. Each service owns its own database and communicates only via APIs and events
(no cross-service database access, per ADR-004).

`demo_service` is the **reference template**: copy it to scaffold a new service, rename the
`demo_service` package and its distribution name, register the new member in the root
`pyproject.toml` workspace, and replace the demo model, health checks, and routes with the real
domain. Follow the Definition of Done in the root `CLAUDE.md`.

Additional services are created as their tasks are implemented (ADR-013), not up front.
