# Multi-stage image for the Process Adapter service.
# Build from the repository root so the uv workspace and shared libraries are available:
#   docker build -f services/process_adapter/Dockerfile -t process-adapter .

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/process_adapter/ services/process_adapter/

RUN uv sync --package process-adapter --frozen --no-dev

FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/libs /app/libs
COPY --from=builder /app/services/process_adapter /app/services/process_adapter

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

CMD ["uvicorn", "process_adapter.main:app", "--host", "0.0.0.0", "--port", "8000"]
