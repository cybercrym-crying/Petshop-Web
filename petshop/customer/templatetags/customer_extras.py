from django import template
from django.utils.translation import gettext_lazy as _

register = template.Library()

# Nama category_label di database memakai kode bahasa Inggris; ini label untuk pengunjung.
CATEGORY_LABELS = {
    "MAKANAN": _("Makanan"),
    "PERLENGKAPAN": _("Perlengkapan"),
    "AKSESORIS": _("Aksesori"),
    "KESEHATAN": _("Kesehatan"),
    "MAINAN": _("Mainan"),
}
# Hewan tujuan & kondisi produk (kode di database -> label untuk pengunjung).
PET_LABEL = {
    "SEMUA": _("Semua Hewan"),
    "KUCING": _("Kucing"),
    "ANJING": _("Anjing"),
    "BURUNG": _("Burung"),
    "KELINCI": _("Kelinci"),
    "IKAN": _("Ikan"),
    "HAMSTER": _("Hamster"),
}
CONDITION_LABEL = {"BARU": _("Baru"), "BEKAS": _("Bekas")}


@register.filter
def category_label(value):
    return CATEGORY_LABELS.get(str(value).upper(), str(value).title())


@register.filter
def pet_label(value):
    return PET_LABEL.get(str(value).upper(), str(value).title())


@register.filter
def condition_label(value):
    return CONDITION_LABEL.get(str(value).upper(), str(value).title())
