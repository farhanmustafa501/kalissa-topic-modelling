#!/bin/bash
set -e

echo "=== Starting application initialization ==="

# Load environment variables from .env file
if [ -f /app/.env ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' /app/.env | xargs)
fi

# Wait for database to be ready
echo "Waiting for database to be ready..."
echo "DATABASE_URL: ${DATABASE_URL:-NOT SET}"

max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
  if python -c "
import sys
import os
# Load .env file manually
from pathlib import Path
from dotenv import load_dotenv
env_path = Path('/app/.env')
if env_path.exists():
    load_dotenv(env_path)

sys.path.insert(0, '/app')
try:
    from app.db import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('Database is ready!')
    sys.exit(0)
except Exception as e:
    print(f'Database not ready: {e}')
    sys.exit(1)
" 2>&1; then
    echo "Database connection successful!"
    break
  fi
  
  attempt=$((attempt + 1))
  if [ $attempt -ge $max_attempts ]; then
    echo "ERROR: Database connection failed after $max_attempts attempts"
    echo "Please check your DATABASE_URL in .env file"
    echo "Continuing anyway - app will retry on first request..."
    break
  fi
  echo "Database is unavailable - sleeping (attempt $attempt/$max_attempts)"
  sleep 2
done

# Run migrations (non-blocking)
echo "Running database migrations..."
alembic upgrade head 2>&1 || echo "Warning: Migrations failed, but continuing..."

echo "=== Starting application server ==="
exec "$@"

