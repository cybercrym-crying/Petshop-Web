from django import template

register = template.Library()

# Nama kategori di database memakai kode bahasa Inggris; ini label untuk pengunjung.
KATEGORI = {"FOOD": "Makanan", "EQUIPMENT": "Perlengkapan", "ACCESSORIES": "Aksesori"}


@register.filter
def kategori(value):
    return KATEGORI.get(str(value).upper(), str(value).title())
