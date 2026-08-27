#!/bin/sh
set -e

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files if needed
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

# Execute the main command
exec "$@"
