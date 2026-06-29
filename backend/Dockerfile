FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Install Python dependencies once at build time (cached layer).
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Copy runtime source so the app can start even when host bind mounts are unavailable.
COPY backend/ ./

CMD ["python", "app.py"]
