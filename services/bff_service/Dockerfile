# Multi-stage image for the BFF service.
# The build context is the repository root so the uv workspace and shared libraries are available.
# Build from the repo root:  docker build -f services/bff_service/Dockerfile -t bff-service .

# --- Builder: resolve and install dependencies into a virtual environment via uv ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Workspace metadata and the members needed to build the BFF service.
COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/bff_service/ services/bff_service/

# Install only the bff-service package and its runtime dependencies (no dev group).
RUN uv sync --package bff-service --frozen --no-dev

# --- Runtime: copy the prepared environment and source ---
FROM python:3.12-slim AS runtime

# Create an unprivileged user to run the service.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# The virtual environment installs workspace members as editable, so the source trees must live at
# the same paths they had during the build.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/libs /app/libs
COPY --from=builder /app/services/bff_service /app/services/bff_service
# The BFF serves the committed OpenAPI contract verbatim as its runtime schema (CR-BFF-R4-MEDIUM-001),
# so the contract file must be present in the image at the repository-relative path.
COPY contracts/openapi/bff-service.v1.yaml /app/contracts/openapi/bff-service.v1.yaml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

CMD ["uvicorn", "bff_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
