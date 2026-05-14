#!/bin/bash
set -e

echo "Running database migrations..."
cd /app
alembic upgrade head

echo "Seeding development auth stub identity..."
# dev_seed is optional — skip cleanly if the module isn't present in this build.
python -m app.core.dev_seed 2>/dev/null || echo "  (skipped: app.core.dev_seed not found)"

echo "Starting application..."
exec "$@"
