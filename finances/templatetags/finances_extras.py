from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def share_for(expense, user):
    """Return the per-user share for this expense."""
    return expense.share_for(user)


@register.filter
def annual_share_for(expense, user):
    """Return the annual per-user amount when the bill comes due."""
    return expense.annual_share_for(user)


@register.simple_tag(takes_context=True)
def amount(context, value):
    cfg = context.get("site_settings")
    if cfg is None:
        from ..models import SiteSettings
        cfg = SiteSettings.get()
    symbol = cfg.currency_symbol
    position = cfg.currency_position
    try:
        formatted = f"{float(value):,.2f}"
    except (TypeError, ValueError):
        formatted = "0.00"
    if position == "before":
        return format_html("{}{}", symbol, formatted)
    return format_html("{}{}", formatted, symbol)
