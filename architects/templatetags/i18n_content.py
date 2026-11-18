from django import template
from django.utils import translation

from poydevor.i18n.content import translate_user_text

register = template.Library()


@register.filter
def tr_content(value):
    """Show something a person wrote in the visitor's language (names and accounts never go through this)."""
    return translate_user_text(value, translation.get_language() or "uz")
