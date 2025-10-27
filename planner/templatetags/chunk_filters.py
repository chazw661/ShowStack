from django import template

register = template.Library()

@register.filter
def get_range(total, step):
    try:
        total = int(total)
        step = int(step)
    except (TypeError, ValueError):
        return []
    return range(0, total, step)

@register.filter
def chunk(seq, size):
    """
    Break a sequence into chunks of length `size`.
    """
    try:
        size = int(size)
    except (TypeError, ValueError):
        return [seq]
    return [ seq[i:i+size] for i in range(0, len(seq), size) ]


@register.filter
def multiply(value, arg):
    """Multiplies the value by the argument."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add(value, arg):
    """Adds the argument to the value."""
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return 0