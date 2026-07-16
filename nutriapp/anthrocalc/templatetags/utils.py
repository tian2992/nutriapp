from django import template

register = template.Library()

@register.filter(name='get_attr')
def get_attr(obj, attr):
    """
    Attempts to get an attribute of an object.
    Supports nested attributes using double underscores or dots.
    """
    if not obj:
        return ""
    
    # Handle both dot and double underscore notation
    parts = attr.replace('__', '.').split('.')
    
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
