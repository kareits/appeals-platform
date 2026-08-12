# Multi-stage image for the document service.
# The build context is the repository root so the uv workspace and shared libraries are available.
# Build from the repo root:  docker build -f services/document_service/Dockerfile -t document-service .

# --- Builder: resolve and install dependencies into a virtual environment via uv ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Workspace metadata and the members needed to build the document service.
COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/document_service/ services/document_service/

# Install only the document-service package and its runtime dependencies (no dev group).
RUN uv sync --package document-service --frozen --no-dev

# --- Runtime: copy the prepared environment and source ---
FROM python:3.12-slim AS runtime

# Create an unprivileged user to run the service. The storage volume is chowned to this user by the
# compose stack; the service never needs root.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# The virtual environment installs workspace members as editable, so the source trees must live at
# the same paths they had during the build.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/libs /app/libs
COPY --from=builder /app/services/document_service /app/services/document_service

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DOCUMENT_STORAGE_ROOT=/var/lib/appeals/files

# Create the storage mount point owned by the runtime user. Docker seeds a *new* named volume from
# the image directory it covers, including its ownership, so the service can write to a fresh volume
# without running as root. An older volume created before this image must be chowned once by an
# operator (see the service README).
RUN mkdir -p /var/lib/appeals/files && chown -R appuser:appuser /var/lib/appeals

USER appuser
EXPOSE 8000

CMD ["uvicorn", "document_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
