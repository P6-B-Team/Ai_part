# Workshop AI Module (WST-FR-14) — Reorder Suggestion & Training Risk Flag
FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code, synthetic data generator, and (if present) pre-trained model artifacts
COPY app ./app
COPY data ./data
COPY models ./models

EXPOSE 8001

# Basic container-level health check, mirrors GET /health
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
