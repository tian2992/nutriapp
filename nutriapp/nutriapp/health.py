"""Lightweight readiness probe used by container healthchecks.

Verifies the default database accepts a read-only round-trip without touching
application tables or running aggregate queries.
"""

from django.db import connection
from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        if row is None or row[0] != 1:
            return HttpResponse("db error\n", status=503, content_type="text/plain")
    except Exception:
        return HttpResponse("db unavailable\n", status=503, content_type="text/plain")
    return HttpResponse("ok\n", content_type="text/plain")
