# syntax=docker/dockerfile:1
# One image: FastAPI serves the API under /api and the built React app everywhere else.

FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STEGOSHIELD_STATIC_DIR=/app/frontend/dist
WORKDIR /app

RUN useradd --create-home --uid 10001 stegoshield
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY core/ core/
COPY ml/ ml/
COPY api/ api/
COPY models/ models/
# The Evaluation Lab reuses the experiment code and serves the saved results CSVs.
COPY experiments/ experiments/
COPY --from=frontend /build/frontend/dist frontend/dist

USER stegoshield
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

# Behind a TLS-terminating reverse proxy, set FORWARDED_ALLOW_IPS to the proxy's address so
# rate limiting sees real client IPs, and STEGOSHIELD_ENABLE_HSTS=1.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--no-access-log"]
