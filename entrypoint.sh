#!/bin/sh
set -e

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files if needed (one-off runs such as scripts/nutri_data.sh
# set SKIP_COLLECTSTATIC=1: they never serve a page)
if [ "${SKIP_COLLECTSTATIC:-0}" != "1" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput || true
fi

# Execute the main command
exec "$@"
