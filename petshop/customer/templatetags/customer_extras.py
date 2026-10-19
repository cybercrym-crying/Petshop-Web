from django import template

register = template.Library()

# Nama kategori di database memakai kode bahasa Inggris; ini label untuk pengunjung.
KATEGORI = {
    "FOOD": "Makanan",
    "EQUIPMENT": "Perlengkapan",
    "ACCESSORIES": "Aksesori",
    "HEALTHCARE": "Kesehatan",
    "TOYS": "Mainan",
    "GROOMING": "Perawatan",
}
# Hewan tujuan & kondisi produk (kode di database -> label untuk pengunjung).
PET_LABEL = {
    "ALL": "Semua Hewan",
    "CAT": "Kucing",
    "DOG": "Anjing",
    "BIRD": "Burung",
    "RABBIT": "Kelinci",
    "FISH": "Ikan",
    "HAMSTER": "Hamster",
}
CONDITION_LABEL = {"NEW": "Baru", "USED": "Bekas"}


@register.filter
def kategori(value):
    return KATEGORI.get(str(value).upper(), str(value).title())


@register.filter
def pet_label(value):
    return PET_LABEL.get(str(value).upper(), str(value).title())


@register.filter
def condition_label(value):
    return CONDITION_LABEL.get(str(value).upper(), str(value).title())
