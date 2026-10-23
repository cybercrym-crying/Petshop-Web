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
    """Kembalikan {msgid: msgstr} dari file .po sederhana (tanpa plural/konteks)."""
    entries, msgid, msgstr, current = {}, None, None, None

    def flush():
        if msgid is not None and msgstr is not None and (msgstr or msgid == ""):
            entries[msgid] = msgstr

    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            msgid, msgstr, current = ast.literal_eval(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, current = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"'):
            text = ast.literal_eval(line)
            if current == "id":
                msgid += text
            elif current == "str":
                msgstr += text
            else:
                raise CommandError(f"{path}:{lineno}: baris lanjutan tanpa msgid/msgstr")
        else:
            raise CommandError(f"{path}:{lineno}: format tidak dikenal (plural/konteks tidak didukung)")
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
