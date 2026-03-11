# ── Stage 1: dependencies ───────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# System deps: Pillow needs these
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: app ─────────────────────────────────────────────
FROM base AS app

WORKDIR /app
COPY . .

# Don't run as root
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
