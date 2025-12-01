FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install -r /app/requirements.txt

COPY . /app

# Make entrypoint script executable (if it exists)
RUN if [ -f /app/docker-entrypoint.sh ]; then chmod +x /app/docker-entrypoint.sh; fi || true

ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "wsgi:app"]


