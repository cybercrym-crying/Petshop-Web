"""Terjemahan teks yang sudah tersimpan (notifikasi, riwayat aktivitas, pesan flash).

Teks seperti "Pesanan #12 dikonfirmasi" disimpan ke database dalam bahasa Indonesia saat
kejadian, lalu dibaca penerima yang mungkin memakai bahasa Inggris. Saat ditampilkan,
teks dicocokkan dengan msgid katalog: persis dulu, lalu pola ber-placeholder
("Pesanan #%(order_pk)s dikonfirmasi") yang nilainya diambil dari teks asli. Teks yang
tidak dikenali tampil apa adanya.
"""

import re
from functools import lru_cache

from django.conf import settings
from django.utils.translation import get_language, gettext, trans_real

PLACEHOLDER = re.compile(r"%\((\w+)\)[sd]")


@lru_cache(maxsize=8)
def _patterns(lang):
    patterns = []
    for msgid in trans_real.translation(lang)._catalog.keys():
        if not isinstance(msgid, str) or "%(" not in msgid:
            continue
        literal = PLACEHOLDER.sub("", msgid).replace("%%", "%")
        letters = len(re.findall(r"[^\W\d_]", literal))
        if letters < 7 and (msgid.startswith("%(") or letters < 3):
            continue  # pola terlalu umum ("%(a)s dari %(b)s") bisa salah menerjemahkan teks bebas
        regex, names, pos = [], [], 0
        for m in PLACEHOLDER.finditer(msgid):
            regex.append(re.escape(msgid[pos:m.start()].replace("%%", "%")))
            regex.append(f"(?P<g{len(names)}>.+?)")
            names.append(m.group(1))
            pos = m.end()
        regex.append(re.escape(msgid[pos:].replace("%%", "%")))
        patterns.append((re.compile("".join(regex), re.S), names, msgid))
    # pola yang lebih spesifik (lebih banyak teks tetap) dicoba lebih dulu
    patterns.sort(key=lambda p: -len(PLACEHOLDER.sub("", p[2])))
    return patterns


@lru_cache(maxsize=4096)
def _translate(text, lang):
    exact = gettext(text)
    if exact != text:
        return exact
    for regex, names, msgid in _patterns(lang):
        m = regex.fullmatch(text)
        if not m:
            continue
        values = {}
        for i, name in enumerate(names):
            value = m.group(f"g{i}")
            if values.setdefault(name, value) != value:
                break  # placeholder yang sama harus bernilai sama
        else:
            translated = gettext(msgid)
            if translated == msgid:
                continue
            values = {k: gettext(v) for k, v in values.items()}
            return PLACEHOLDER.sub(lambda g: "%(" + g.group(1) + ")s", translated) % values
    return text


def translate_stored(text):
    """Teks tersimpan dalam bahasa aktif; teks yang tidak dikenali dikembalikan apa adanya."""
    if not text or not isinstance(text, str):
        return text
    # Bahasa Indonesia juga lewat sini: katalog "id" menyeragamkan istilah (order -> pesanan).
    return _translate(text, get_language() or settings.LANGUAGE_CODE)
