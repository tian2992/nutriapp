import math
from decimal import Decimal
import pygrowup.tables.by_day.lfa as lfa_day
import pygrowup.tables.by_day.wfa as wfa_day
import pygrowup.tables.by_day.wfh as wfh_day
import pygrowup.tables.by_day.wfl as wfl_day
import pygrowup.tables.by_month.lfa as lfa_month
import pygrowup.tables.by_month.wfa as wfa_month


def normalize_sex(sex: str) -> str:
    """Normalize sex string to 'male' or 'female'."""
    if not sex:
        raise ValueError("Sex must be specified")
    s = str(sex).strip().lower()
    if s in ("male", "m", "1", "boy", "masculino", "varon", "niño"):
        return "male"
    elif s in ("female", "f", "2", "girl", "femenino", "mujer", "niña"):
        return "female"
    raise ValueError(f"Unknown or unsupported sex: {sex}")


def lms_inverse(l, m, s, z: float) -> float:
    """
    Inverse of the Cole-Green Box-Cox LMS formula (BCPE distribution with tau=2).
    Given L, M, S parameters and Z-score, returns the measurement value Y.

    If L != 0: Y = M * (1 + L * S * Z) ** (1 / L)
    If L == 0: Y = M * exp(S * Z)
    """
    l = float(l)
    m = float(m)
    s = float(s)
    z = float(z)

    if l != 0.0:
        base = 1.0 + l * s * z
        if base <= 0:
            return float("nan")
        return m * (base ** (1.0 / l))
    else:
        return m * math.exp(s * z)


def get_lms_for_point(indicator: str, sex: str, point: float | int | Decimal) -> dict:
    """
    Retrieves the LMS parameters {'l', 'm', 's'} for a given indicator, sex, and point.
    - For 'hfa', 'lfa', 'lhfa', 'wfa': point is age in months.
    - For 'wfh': point is standing height in cm (range 65 - 120 cm).
    - For 'wfl': point is recumbent length in cm (range 45 - 110 cm).
    """
    norm_sex = normalize_sex(sex)
    ind = str(indicator).strip().lower()

    if ind in ("hfa", "lfa", "lhfa"):
        days_per_month = 365.25 / 12.0
        t = int(round(float(point) * days_per_month))
        if t <= 1856:
            t_clamped = max(0, min(1856, t))
            return lfa_day.DATA[norm_sex][t_clamped]
        else:
            m_val = int(round(float(point)))
            m_clamped = max(61, min(228, m_val))
            return lfa_month.DATA[norm_sex][m_clamped]

    elif ind == "wfa":
        days_per_month = 365.25 / 12.0
        t = int(round(float(point) * days_per_month))
        if t <= 1856:
            t_clamped = max(0, min(1856, t))
            return wfa_day.DATA[norm_sex][t_clamped]
        else:
            m_val = int(round(float(point)))
            m_clamped = max(61, min(120, m_val))
            return wfa_month.DATA[norm_sex][m_clamped]

    elif ind == "wfh":
        val = Decimal(str(round(float(point), 1))).quantize(Decimal("0.1"))
        val_clamped = max(Decimal("65.0"), min(Decimal("120.0"), val))
        return wfh_day.DATA[norm_sex][val_clamped]

    elif ind == "wfl":
        val = Decimal(str(round(float(point), 1))).quantize(Decimal("0.1"))
        val_clamped = max(Decimal("45.0"), min(Decimal("110.0"), val))
        return wfl_day.DATA[norm_sex][val_clamped]

    else:
        raise ValueError(f"Unknown indicator '{indicator}'. Supported: 'hfa', 'wfa', 'wfh', 'wfl'")


def reference_band(indicator: str, sex: str, points: list[float | int | Decimal]) -> list[dict]:
    """
    Calculates WHO reference bands (-2SD, -1SD, 0, +1SD, +2SD) for given points.

    Args:
        indicator: "hfa" | "lfa" | "lhfa" | "wfa" | "wfh" | "wfl"
        sex: "male" | "female" (or "m" / "f")
        points: ages in months (for hfa/wfa) or heights/lengths in cm (for wfh/wfl)

    Returns:
        list of dicts, each containing:
        {"x": point, "-2SD": val, "-1SD": val, "0": val, "+1SD": val, "+2SD": val}
    """
    results = []
    for pt in points:
        lms = get_lms_for_point(indicator, sex, pt)
        l, m, s = lms["l"], lms["m"], lms["s"]
        results.append({
            "x": pt,
            "-2SD": lms_inverse(l, m, s, -2.0),
            "-1SD": lms_inverse(l, m, s, -1.0),
            "0": lms_inverse(l, m, s, 0.0),
            "+1SD": lms_inverse(l, m, s, 1.0),
            "+2SD": lms_inverse(l, m, s, 2.0),
        })
    return results
