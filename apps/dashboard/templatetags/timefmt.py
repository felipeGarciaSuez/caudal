"""Human-readable durations in Spanish for templates."""

from datetime import timedelta

from django import template

register = template.Library()


@register.filter
def duration_es(value):
    """Render a timedelta as friendly es-AR text.

    Rounds up to the next whole minute: "1 hora", "45 minutos",
    "1 hora y 30 minutos". Non-timedelta or non-positive -> "un momento".
    """
    if not isinstance(value, timedelta):
        return "un momento"
    total_minutes = int((value.total_seconds() + 59) // 60)  # round up
    if total_minutes <= 0:
        return "un momento"
    hours, minutes = divmod(total_minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hora" if hours == 1 else f"{hours} horas")
    if minutes:
        parts.append(f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos")
    return " y ".join(parts)
