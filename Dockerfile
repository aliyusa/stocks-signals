# One container for hosting (Render): builds the React app, then serves it and the API from FastAPI.
# Same origin means httpOnly SameSite cookies work and no CORS is needed.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATIC_DIR=/app/static ENVIRONMENT=production COOKIE_SECURE=true
WORKDIR /app
RUN useradd --create-home appuser
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./static
USER appuser
EXPOSE 8000
# Render sets $PORT. Proxy headers let rate limits and lockouts see the real client IP, not Render's proxy.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
