from django import template

register = template.Library()

# Nama category_label di database memakai kode bahasa Inggris; ini label untuk pengunjung.
CATEGORY_LABELS = {
    "MAKANAN": "Makanan",
    "PERLENGKAPAN": "Perlengkapan",
    "AKSESORIS": "Aksesori",
    "KESEHATAN": "Kesehatan",
    "MAINAN": "Mainan",
}
# Hewan tujuan & kondisi produk (kode di database -> label untuk pengunjung).
PET_LABEL = {
    "SEMUA": "Semua Hewan",
    "KUCING": "Kucing",
    "ANJING": "Anjing",
    "BURUNG": "Burung",
    "KELINCI": "Kelinci",
    "IKAN": "Ikan",
    "HAMSTER": "Hamster",
}
CONDITION_LABEL = {"BARU": "Baru", "BEKAS": "Bekas"}


@register.filter
def category_label(value):
    return CATEGORY_LABELS.get(str(value).upper(), str(value).title())


@register.filter
def pet_label(value):
    return PET_LABEL.get(str(value).upper(), str(value).title())


@register.filter
def condition_label(value):
    return CONDITION_LABEL.get(str(value).upper(), str(value).title())
