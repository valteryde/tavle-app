FROM node:22-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json ./
COPY src ./src
COPY public ./public
ENV VITE_TAVLE_PUBLIC_URL=http://localhost:5050
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY schemas ./schemas
COPY --from=frontend /app/dist ./static

ENV STATIC_DIR=/app/static \
    METADATA_DB_PATH=/data/metadata.db \
    TAVLE_INTERNAL_URL=http://tavle:5050 \
    TAVLE_PUBLIC_URL=http://localhost:5050

RUN mkdir -p /data
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/api/status || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
