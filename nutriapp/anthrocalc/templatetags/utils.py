from django import template

register = template.Library()


@register.filter(name="get_attr")
def get_attr(obj, attr):
    """
    Attempts to get an attribute of an object.
    Supports nested attributes using double underscores or dots.
    """
    if not obj:
        return ""

    # Handle both dot and double underscore notation
    parts = attr.replace("__", ".").split(".")

    val = obj
    for part in parts:
        try:
            val = getattr(val, part)
        except (AttributeError, TypeError):
            try:
                # Try as dictionary if getattr fails
                val = val.get(part)
            except (AttributeError, TypeError):
                return ""

        if callable(val):
            try:
                val = val()
            except:
                pass

    return val


@register.filter(name="kg_to_lb")
def kg_to_lb(weight, precision=1):
    """Converts a weight in kilograms to pounds."""
    try:
        kg = float(weight)
        lb = kg * 2.20462
        precision = int(precision)
        return format(lb, f".{precision}f")
    except (TypeError, ValueError):
        return ""
