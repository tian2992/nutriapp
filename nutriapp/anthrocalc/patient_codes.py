"""Patient code generation: QA + municipio(3) + community(3) + NNN.

Fill MUNICIPALITY_CODES / COMMUNITY_CODES with real 3-char codes when known.
Until then, segments fall back to trimming the name. Callers may also pass
an optional map to override the module defaults without changing the
Community argument.
"""

from __future__ import annotations

import re
import unicodedata

from django.conf import settings

# Org base; override with settings.PATIENT_CODE_ORG_PREFIX when needed.
DEFAULT_ORG_PREFIX = "QA"
_SEGMENT_LEN = 3
_FALLBACK_SEGMENT = "X" * _SEGMENT_LEN

# Hardcoded name → 3-char code maps. TODO: add entries for comunidad later.
MUNICIPALITY_CODES: dict[str, str] = {}
COMMUNITY_CODES: dict[str, str] = {}


def get_org_prefix() -> str:
    return getattr(settings, "PATIENT_CODE_ORG_PREFIX", DEFAULT_ORG_PREFIX)


def _letters_only(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return "".join(c for c in without_accents.upper() if c.isalpha())


def trim_segment(value: str, length: int = _SEGMENT_LEN) -> str:
    """First `length` letters of value; pad with X if shorter."""
    letters = _letters_only(value)
    if not letters:
        return _FALLBACK_SEGMENT
    return letters[:length].ljust(length, "X")


def _segment_from_map_or_trim(name: str, code_map: dict[str, str]) -> str:
    if name in code_map:
        return code_map[name]
    return trim_segment(name)


def municipality_code(municipality: str, code_map: dict[str, str] | None = None) -> str:
    """3-char municipio code from map, or trim of the name."""
    return _segment_from_map_or_trim(municipality, code_map if code_map is not None else MUNICIPALITY_CODES)


def community_code(community_name: str, code_map: dict[str, str] | None = None) -> str:
    """3-char community code from map, or trim of the name."""
    return _segment_from_map_or_trim(community_name, code_map if code_map is not None else COMMUNITY_CODES)


def code_prefix_for_community(
    community,
    org_prefix: str | None = None,
    municipality_map: dict[str, str] | None = None,
    community_map: dict[str, str] | None = None,
) -> str:
    """Build QA + muni + community prefix for a Community instance."""
    org = org_prefix if org_prefix is not None else get_org_prefix()
    if community is None:
        return f"{org}{_FALLBACK_SEGMENT}{_FALLBACK_SEGMENT}"
    muni = municipality_code(community.municipality or "", code_map=municipality_map)
    comm = community_code(community.name or "", code_map=community_map)
    return f"{org}{muni}{comm}"


def next_sequence_number(prefix: str, existing_codes) -> int:
    """Next free 3-digit sequence for codes starting with `prefix`."""
    max_n = 0
    prefix_len = len(prefix)
    for code in existing_codes:
        if not code or not str(code).startswith(prefix):
            continue
        suffix = str(code)[prefix_len:]
        if re.fullmatch(r"\d+", suffix):
            max_n = max(max_n, int(suffix))
    return max_n + 1


def generate_patient_code(
    community=None,
    org_prefix: str | None = None,
    municipality_map: dict[str, str] | None = None,
    community_map: dict[str, str] | None = None,
) -> str:
    """Build the next patient code for a Community (QA + muni + community + NNN)."""
    from .models import Patient

    prefix = code_prefix_for_community(
        community,
        org_prefix=org_prefix,
        municipality_map=municipality_map,
        community_map=community_map,
    )
    existing = Patient.objects.filter(code__startswith=prefix).values_list("code", flat=True)
    seq = next_sequence_number(prefix, existing)
    return f"{prefix}{seq:03d}"
