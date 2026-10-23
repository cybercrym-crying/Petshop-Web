import ast
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation.template import templatize

from common.management.commands.build_locale import parse_po
from service.models import BookingStatus

PO_FILE = Path(settings.BASE_DIR) / "locale" / "en" / "LC_MESSAGES" / "django.po"
GETTEXT_CALL = re.compile(r"""gettext\((u?'(?:[^'\\]|\\.)*'|u?"(?:[^"\\]|\\.)*")\)""")
PLACEHOLDER = re.compile(r"%\(\w+\)s")


def template_msgids():
    """Semua teks {% translate %} / {% blocktranslate %} di template proyek (cara yang sama dengan makemessages)."""
    found = {}
    for path in Path(settings.BASE_DIR).glob("*/templates/**/*.html"):
        for m in GETTEXT_CALL.finditer(templatize(path.read_text(encoding="utf-8"))):
            found.setdefault(ast.literal_eval(m.group(1)), str(path))
    for path in (Path(settings.BASE_DIR) / "templates").glob("**/*.html"):
        for m in GETTEXT_CALL.finditer(templatize(path.read_text(encoding="utf-8"))):
            found.setdefault(ast.literal_eval(m.group(1)), str(path))
    return found


class TranslationCatalogTests(TestCase):
    def test_every_template_text_has_an_english_translation(self):
        catalog = parse_po(PO_FILE)
        missing = {msgid: where for msgid, where in template_msgids().items() if not catalog.get(msgid)}
        self.assertEqual(missing, {}, "Teks belum diterjemahkan; tambahkan ke django.po lalu build_locale")

    def test_translations_keep_the_same_placeholders(self):
        for msgid, msgstr in parse_po(PO_FILE).items():
            with self.subTest(msgid=msgid):
                self.assertEqual(sorted(PLACEHOLDER.findall(msgid)), sorted(PLACEHOLDER.findall(msgstr)))
                self.assertEqual(msgid.count("%%"), msgstr.count("%%"))

    def test_compiled_catalog_is_up_to_date(self):
        mo = PO_FILE.with_suffix(".mo")
        self.assertTrue(mo.exists(), "Jalankan python manage.py build_locale")
        self.assertGreaterEqual(mo.stat().st_mtime, PO_FILE.stat().st_mtime - 1)

    def test_status_labels_follow_the_active_language(self):
        with translation.override("en"):
            self.assertEqual(str(BookingStatus.READY.label), "Ready for pickup")
        with translation.override("id"):
            self.assertEqual(str(BookingStatus.READY.label), "Siap diambil")


class LanguageToggleTests(TestCase):
    def test_default_is_indonesian_even_for_english_browsers(self):
        r = self.client.get(reverse("customer:home"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        self.assertContains(r, '<html lang="id">')
        self.assertContains(r, ">Beranda</a>")
        self.assertEqual(r["Content-Language"], "id")

    def test_toggle_switches_to_english_and_back(self):
        r = self.client.post(reverse("set_language"), {"language": "en", "next": reverse("customer:shop")})
        self.assertRedirects(r, reverse("customer:shop"), fetch_redirect_response=False)
        self.assertEqual(r.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        r = self.client.get(reverse("customer:home"))
        self.assertContains(r, '<html lang="en">')
        self.assertContains(r, ">Home</a>")
        self.assertContains(r, ">Shop</a>")
        self.assertNotContains(r, ">Beranda</a>")
        self.client.post(reverse("set_language"), {"language": "id", "next": "/"})
        self.assertContains(self.client.get(reverse("customer:home")), ">Beranda</a>")

    def test_unknown_language_cookie_falls_back_to_indonesian(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "fr"
        self.assertContains(self.client.get(reverse("customer:home")), '<html lang="id">')

    def test_toggle_rejects_an_external_next_url(self):
        r = self.client.post(reverse("set_language"), {"language": "en", "next": "https://contoh-jahat.test/"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("contoh-jahat", r["Location"])

    def test_toggle_is_on_login_and_public_pages(self):
        for name in ("login_form", "customer:home", "service:catalog"):
            with self.subTest(name=name):
                self.assertContains(self.client.get(reverse(name)), 'class="lang-toggle')
