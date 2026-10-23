"""Penjaga tampilan: aset tidak diambil dari internet, teks bawaan berbahasa Indonesia, warna aksi seragam."""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.utils import translation

from account.models import Role, User

BASE = Path(settings.BASE_DIR)


def templates():
    paths = list(BASE.glob("*/templates/**/*.html")) + list((BASE / "templates").glob("**/*.html"))
    return [p for p in paths if "_unused" not in p.parts]


class AssetTests(TestCase):
    def test_icons_fonts_and_bootstrap_are_served_locally(self):
        cdn = re.compile(r"https://(cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|fonts\.googleapis\.com|fonts\.gstatic\.com|unpkg\.com)")
        found = [str(p.relative_to(BASE)) for p in templates() if cdn.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(found, [], "simpan aset di static/vendor/ agar tetap tampil saat internet lambat")
        for path in ("vendor/bootstrap-icons/fonts/bootstrap-icons.woff2", "vendor/fontawesome/webfonts/fa-solid-900.woff2",
                     "vendor/fonts/plus-jakarta-sans-latin-wght-normal.woff2"):
            self.assertTrue((BASE / "static" / path).exists(), path)

    def test_every_layout_loads_the_shared_action_colours(self):
        missing = [str(p.relative_to(BASE)) for p in templates()
                   if "</head>" in p.read_text(encoding="utf-8") and "css/actions.css" not in p.read_text(encoding="utf-8")]
        self.assertEqual(missing, [])


class LanguageTests(TestCase):
    def test_blank_choice_is_indonesian(self):
        from django.db.models.fields import BLANK_CHOICE_LABEL

        with translation.override("id"):
            self.assertEqual(str(BLANK_CHOICE_LABEL), "- Pilih -")

    def test_complaint_form_has_no_english_placeholder(self):
        User.objects.create_user("pel", password="x", role=Role.CUSTOMER)
        self.client.login(username="pel", password="x")
        r = self.client.get("/komplain/")
        self.assertNotContains(r, "Select an option")
        self.assertContains(r, "- Pilih -")
