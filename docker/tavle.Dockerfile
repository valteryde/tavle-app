# Standalone Tavle image (cloned at build time — no submodule required).
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/Den-Frie-Digitale-Skole/tavle.git /src

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /src/requirements.txt gunicorn

FROM python:3.11-slim AS production

RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* && apt-get clean

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY --from=builder --chown=appuser:appgroup /src /app
RUN mkdir -p /app/logs && chown appuser:appgroup /app/logs

USER appuser
ENV FLASK_ENV=production HOST=0.0.0.0 PORT=5050 LOG_DIR=/app/logs
EXPOSE 5050

HEALTHCHECK --interval=15s --timeout=10s --start-period=20s --retries=5 \
  CMD curl -f http://localhost:5050/health || exit 1

CMD ["gunicorn", "--worker-class", "eventlet", "--workers", "1", \
  "--bind", "0.0.0.0:5050", "--timeout", "120", "server:app"]
