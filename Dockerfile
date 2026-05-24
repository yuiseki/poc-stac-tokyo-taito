FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/

# ---

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/src ./src

# GeoJSON files required for dynamic MVT tile index
COPY docs/data/ ./docs/data/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8080

CMD uvicorn poc_stac_tokyo_taito.app:app --host 0.0.0.0 --port ${PORT:-8080}
