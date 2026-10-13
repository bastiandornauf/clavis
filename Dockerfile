FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY manage.py ./
COPY config ./config
COPY apps ./apps
COPY templates ./templates
COPY static ./static

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV CLAVIS_DATA_DIR=/data
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
