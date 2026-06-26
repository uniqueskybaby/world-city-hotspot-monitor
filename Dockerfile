FROM node:22-bookworm AS frontend
WORKDIR /app
COPY package.json package-lock.json* .npmrc ./
RUN npm install
COPY index.html vite.config.mjs ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV DATA_DIR=/app/data
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV ENABLE_SCHEDULER=true
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential curl \
  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY --from=frontend /app/dist ./dist
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8000}"]
