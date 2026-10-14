"""Text search for the patient list.

PostgreSQL matches name and code with ``unaccent`` and case-insensitive
contains, so "Nimacabaj" finds "Nímacabaj" and the reverse. Other databases,
including the SQLite test database, use ``icontains`` only and do not strip
accents.
"""

from __future__ import annotations

from django.contrib.postgres.lookups import Unaccent
from django.db import connection
from django.db.models import CharField, Q, QuerySet, TextField

_unaccent_registered = False


def _register_unaccent_lookup() -> None:
    """Register Django's Unaccent transform on text fields once."""
    global _unaccent_registered
    if _unaccent_registered:
        return
    CharField.register_lookup(Unaccent)
    TextField.register_lookup(Unaccent)
    _unaccent_registered = True


def filter_patients_by_text(qs: QuerySet, text: str | None) -> QuerySet:
    """Keep patients whose name or code contains ``text``.

    Empty text leaves ``qs`` unchanged. On PostgreSQL the match ignores
    accents and case. On SQLite it is a case-insensitive substring match.
    """
    if text is None:
        return qs
    text = str(text).strip()
    if not text:
        return qs
    if connection.vendor == "postgresql":
        _register_unaccent_lookup()
        return qs.filter(Q(name__unaccent__icontains=text) | Q(code__unaccent__icontains=text))
    return qs.filter(Q(name__icontains=text) | Q(code__icontains=text))
