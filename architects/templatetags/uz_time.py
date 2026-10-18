from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def uz_ago(value):
    """A short Uzbek "how long ago", e.g. "bugun", "3 kun oldin", "2 hafta oldin"."""
    if not value:
        return ""
    days = (timezone.now() - value).days
    if days < 1:
        return "Bugun"
    if days < 7:
        return f"{days} kun oldin"
    if days < 30:
        return f"{days // 7} hafta oldin"
    if days < 365:
        return f"{days // 30} oy oldin"
    return f"{days // 365} yil oldin"
