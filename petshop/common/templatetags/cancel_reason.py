from django import template

from common.cancel import OTHER, REASONS

register = template.Library()


@register.inclusion_tag("partials/_cancel_reason.html", takes_context=True)
def cancel_form(context, kind, action, label, uid, back="", order_action=False, confirm=""):
    """Tombol "Batalkan" yang membuka form alasan (pilihan cepat + keterangan)."""
    return {
        "csrf_token": context.get("csrf_token"),
        "reasons": REASONS[kind], "other": OTHER, "action": action, "label": label,
        "uid": uid, "back": back, "order_action": order_action, "confirm": confirm,
        "staff": kind.startswith("staff"),
    }
