#!/bin/bash
set -e

echo "Running database migrations..."
cd /app
alembic upgrade head

echo "Seeding development auth stub identity..."
python -m app.core.dev_seed

echo "Starting application..."
exec "$@"
