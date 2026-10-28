"""Kompilasi file terjemahan .po menjadi .mo tanpa perlu GNU gettext.

Pakai: python manage.py build_locale
Jalankan setiap kali locale/<bahasa>/LC_MESSAGES/django.po diubah.
"""

import ast
import struct
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def parse_po(path):
    """Kembalikan {msgid: msgstr} dari file .po sederhana (tanpa konteks).

    Entri jamak (msgid_plural + msgstr[n]) disimpan dengan kunci "tunggal\\0jamak" dan
    nilai "bentuk0\\0bentuk1", sama seperti isi file .mo.
    """
    entries, msgid, plural, forms, current = {}, None, None, {}, None

    def flush():
        if msgid is None:
            return
        if plural is not None:
            if forms and all(forms.values()):
                entries[f"{msgid}\0{plural}"] = "\0".join(forms[i] for i in sorted(forms))
        elif forms.get(None) or (msgid == "" and None in forms):
            entries[msgid] = forms[None]

    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            msgid, plural, forms, current = ast.literal_eval(line[6:]), None, {}, "id"
        elif line.startswith("msgid_plural "):
            plural, current = ast.literal_eval(line[13:]), "plural"
        elif line.startswith("msgstr["):
            index, text = line[7:].split("]", 1)
            current = int(index)
            forms[current] = ast.literal_eval(text.strip())
        elif line.startswith("msgstr "):
            current = None
            forms[None] = ast.literal_eval(line[7:])
        elif line.startswith('"'):
            text = ast.literal_eval(line)
            if current == "id":
                msgid += text
            elif current == "plural":
                plural += text
            elif current in forms:
                forms[current] += text
            else:
                raise CommandError(f"{path}:{lineno}: baris lanjutan tanpa msgid/msgstr")
        else:
            raise CommandError(f"{path}:{lineno}: format tidak dikenal (konteks tidak didukung)")
    flush()
    return entries


def write_mo(entries, path):
    """Tulis katalog dalam format GNU .mo (little-endian)."""
    keys = sorted(entries)
    ids = [k.encode("utf-8") for k in keys]
    strs = [entries[k].encode("utf-8") for k in keys]
    header_size = 7 * 4
    table_size = len(keys) * 8
    id_start = header_size + 2 * table_size
    str_start = id_start + sum(len(i) + 1 for i in ids)
    id_table, str_table, offset = [], [], id_start
    for i in ids:
        id_table += [len(i), offset]
        offset += len(i) + 1
    offset = str_start
    for s in strs:
        str_table += [len(s), offset]
        offset += len(s) + 1
    data = struct.pack("<7I", 0x950412DE, 0, len(keys), header_size, header_size + table_size, 0, 0)
    data += struct.pack(f"<{len(id_table)}I", *id_table)
    data += struct.pack(f"<{len(str_table)}I", *str_table)
    data += b"".join(i + b"\0" for i in ids) + b"".join(s + b"\0" for s in strs)
    Path(path).write_bytes(data)


class Command(BaseCommand):
    help = "Kompilasi locale/*/LC_MESSAGES/django.po menjadi .mo (tanpa GNU gettext)."

    def handle(self, *args, **options):
        found = False
        for base in settings.LOCALE_PATHS:
            for po in sorted(Path(base).glob("*/LC_MESSAGES/django.po")):
                found = True
                entries = parse_po(po)
                write_mo(entries, po.with_suffix(".mo"))
                self.stdout.write(f"{po.parent.parent.name}: {len(entries) - 1} terjemahan -> {po.with_suffix('.mo').name}")
        if not found:
            raise CommandError("Tidak ada file django.po di LOCALE_PATHS.")
