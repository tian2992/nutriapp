# Stage 1: Builder
FROM python:3.13-slim AS builder

# git is required for pygrowup2 (git+https://github.com/jbaldivieso/pygrowup2.git)
# build-essential is required for numpy/pandas/matplotlib C-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  git-core \
  libpq-dev \
  && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final
FROM python:3.13-slim AS final

LABEL authors="tian"

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PATH="/opt/venv/bin:$PATH" \
  PYTHONPATH="/app"

# Runtime dependencies:
# - libpq5: Postgres client
# - curl: Healthchecks
# - libpng16-16 & libfreetype6: Required by Matplotlib for rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    libpng16-16 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN adduser -u 1000 --disabled-password --gecos "" appuser

RUN mkdir -p /app/static /app/media && chown -R appuser:appuser /app/static /app/media

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
# Copying the contents of the nutriapp folder so manage.py is in /app
COPY --chown=appuser:appuser nutriapp /app

USER appuser

EXPOSE 8000

# Health check (assuming admin is enabled in urls.py)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/admin/ || exit 1

# Gunicorn setup for nutriapp project structure
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "nutriapp.wsgi:application"]