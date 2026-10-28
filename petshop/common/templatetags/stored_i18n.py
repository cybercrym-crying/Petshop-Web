from django import template

from common.stored_i18n import translate_stored

register = template.Library()


@register.filter
def tr(text):
    """Teks notifikasi/riwayat yang tersimpan, ditampilkan dalam bahasa aktif."""
    return translate_stored(text)
