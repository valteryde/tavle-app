FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 https://github.com/Den-Frie-Digitale-Skole/tavle.git /tmp/tavle \
    && cp -a /tmp/tavle/. /app/ \
    && rm -rf /tmp/tavle

RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /data/tavle/logs

ENV PORT=5050 TAVLE_HOST=0.0.0.0 WHITEBOARD_DATA_DIR=/data/tavle
EXPOSE 5050
HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=5 \
  CMD curl -f http://localhost:5050/health || exit 1
CMD ["python", "server.py"]
