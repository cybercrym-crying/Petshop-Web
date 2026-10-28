"""Gambar untuk data demo: foto produk, foto profil, foto hewan, dan foto bukti.

- Foto produk: ilustrasi kemasan per produk di demo_assets/products/ (dibuat khusus untuk demo).
- Foto profil: ilustrasi DiceBear "notionists" (lisensi CC0) di demo_assets/avatars/.
- Foto hewan & bukti antar: potongan foto hewan/paket yang sudah ada di static/ proyek.
Semua file disimpan dengan awalan "demo-" supaya bisa dikenali dan dipulihkan.
"""

import io
import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / "demo_assets"
AVATAR_COUNT = 48

# Foto hewan sumber: (file static, kotak potong kiri, atas, sisi) -> dipotong persegi.
PET_SOURCES = {
    "kucing-putih": ("customer/img/about-health.jpg", (450, 1950, 2500)),
    "kucing-belang": ("customer/img/about-collage.jpg", (1700, 0, 3900)),
    "kucing-bengal": ("customer/img/category-equipment.jpg", (900, 300, 4800)),
    "anjing-golden": ("customer/img/category-toys.jpg", (0, 1000, 3150)),
    "anjing-bulldog": ("customer/img/hero-home-dog.png", (560, 190, 720)),
}
# Ras -> foto yang cocok. Ras tanpa foto yang cocok dibiarkan tanpa foto (seperti pemilik yang belum mengunggah).
BREED_PHOTOS = {
    "Persia": ["kucing-putih"],
    "Anggora": ["kucing-putih"],
    "Domestik": ["kucing-belang"],
    "Bengal": ["kucing-bengal"],
    "Golden Retriever": ["anjing-golden"],
    "French Bulldog": ["anjing-bulldog"],
}
DELIVERY_SOURCE = ("customer/img/about-order.jpg", (300, 1300, 3600))

_cache = {}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _font(size):
    return ImageFont.load_default(size=size)


def _jpeg(img, name, quality=84):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    return ContentFile(buf.getvalue(), name=name)


def _file(path, name):
    return ContentFile(path.read_bytes(), name=name) if path.exists() else None


def product_photo(product_name):
    """Foto produk dari demo_assets/products/<slug>.jpg; None bila belum ada."""
    return _file(ASSETS / "products" / f"{slug(product_name)}.jpg", f"demo-{slug(product_name)}.jpg")


def avatar(n):
    """Foto profil ke-n (1..AVATAR_COUNT, berulang)."""
    n = (n - 1) % AVATAR_COUNT + 1
    return _file(ASSETS / "avatars" / f"orang-{n:02d}.jpg", f"demo-orang-{n:02d}.jpg")


def _square(key, source, size):
    """Potongan persegi dari foto static, di-cache supaya file besar tidak dibuka berulang."""
    cache_key = (key, size)
    if cache_key not in _cache:
        path, (left, top, side) = source
        found = finders.find(path)
        if not found:
            return None
        with Image.open(found) as img:
            img = img.convert("RGB")
            side = min(side, img.width - left, img.height - top)
            img = img.crop((left, top, left + side, top + side))
            img.thumbnail((size, size))
            _cache[cache_key] = img.copy()
    return _cache[cache_key].copy()


def _variant(img, seed):
    """Variasi ringan (cermin, zoom, warna) supaya foto berulang tidak identik."""
    if seed % 2:
        img = ImageOps.mirror(img)
    zoom = (seed // 2) % 3
    if zoom:
        cut = int(img.width * 0.06 * zoom)
        dx = cut if seed % 3 else cut // 2
        img = img.crop((dx, cut // 2, img.width - (cut - dx) - cut // 2, img.height - cut)).resize(img.size)
    return img


def _stamp(img, lines):
    """Tulisan kecil di bawah foto, seperti cap waktu kamera aplikasi."""
    draw = ImageDraw.Draw(img, "RGBA")
    h = 26 + 24 * len(lines)
    draw.rectangle([0, img.height - h, img.width, img.height], fill=(0, 0, 0, 120))
    for i, text in enumerate(lines):
        draw.text((16, img.height - h + 12 + i * 24), text, fill=(255, 255, 255, 235), font=_font(18))
    return img


def pet_key(breed, seed):
    keys = BREED_PHOTOS.get(breed or "")
    return keys[seed % len(keys)] if keys else None


def pet_photo(breed, seed, stamp=None, size=640, name="demo-hewan.jpg"):
    """Foto hewan sesuai ras; None bila ras belum punya foto yang cocok."""
    key = pet_key(breed, seed)
    if not key:
        return None
    img = _square(key, PET_SOURCES[key], size)
    if img is None:
        return None
    img = _variant(img, seed)
    if stamp:
        img = _stamp(img, stamp)
    return _jpeg(img, name)


def delivery_photo(order, stamp):
    img = _square("antar", DELIVERY_SOURCE, 640)
    if img is None:
        return None
    return _jpeg(_stamp(_variant(img, order.pk), stamp), f"demo-antar-{order.pk}.jpg")


def transfer_receipt(pk, amount, sender, bank, paid_at, note, name):
    """Tangkapan layar transfer bergaya m-banking umum, ditandai sebagai contoh di bagian bawah."""
    img = Image.new("RGB", (540, 900), "#f5f7fb")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 540, 70], fill="#1f3c88")
    d.text((24, 22), "m-Banking", fill="white", font=_font(26))
    d.ellipse([220, 120, 320, 220], fill="#2fb36d")
    d.line([(244, 172), (264, 192), (298, 150)], fill="white", width=10)
    d.text((270, 250), "Transfer Berhasil", fill="#1d2433", font=_font(30), anchor="mm")
    amount = f"Rp {amount:,}".replace(",", ".")
    d.text((270, 300), amount, fill="#1d2433", font=_font(40), anchor="mm")
    rows = [
        ("Tanggal", paid_at.strftime("%d/%m/%Y %H:%M") + " WITA"),
        ("No. referensi", f"{paid_at:%y%m%d}{pk:06d}{(pk * 7919) % 1000:03d}"),
        ("Dari", sender[:24]),
        ("Ke", f"{bank.holder[:22]}"),
        ("Bank tujuan", f"{bank.bank} {bank.number}"),
        ("Berita", note),
    ]
    y = 370
    d.rounded_rectangle([24, y - 20, 516, y + 62 * len(rows)], radius=18, fill="white")
    for label, value in rows:
        d.text((48, y + 8), label, fill="#7a8194", font=_font(20))
        d.text((492, y + 8), value, fill="#1d2433", font=_font(20), anchor="ra")
        y += 62
    d.text((270, 870), "Data contoh aplikasi demo", fill="#a3a9b8", font=_font(16), anchor="mm")
    return _jpeg(img, name)


def is_demo_file(field):
    """Kosong, atau file demo yang tercatat tetapi hilang dari folder media."""
    if not field:
        return True
    if not Path(field.name).name.startswith("demo-"):
        return False
    return not field.storage.exists(field.name)
