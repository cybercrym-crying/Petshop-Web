from django import template

register = template.Library()


@register.filter
def rupiah(value):
    """24000 -> '24.000' (pemisah ribuan titik, tanpa desimal)."""
    try:
        return f"{int(value or 0):,}".replace(",", ".")
    except (TypeError, ValueError):
        return value
