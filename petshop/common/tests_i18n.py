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
STRING = r"u?'(?:[^'\\]|\\.)*'|u?\"(?:[^\"\\]|\\.)*\""
TEMPLATE_UNDERSCORE = re.compile(rf"(?<![\w.])_\(({STRING})\)")
NGETTEXT_CALL = re.compile(rf"ngettext\(({STRING}),\s*({STRING}),")
PLACEHOLDER = re.compile(r"%\(\w+\)s")


def template_msgids():
    """Semua teks {% translate %} / {% blocktranslate %} di template proyek (cara yang sama dengan makemessages)."""
    found = {}
    base = Path(settings.BASE_DIR)
    for path in [*base.glob("*/templates/**/*.html"), *(base / "templates").glob("**/*.html")]:
        raw = path.read_text(encoding="utf-8")
        for m in TEMPLATE_UNDERSCORE.finditer(raw):  # _("...") di argumen tag, mis. {% include ... with hint=_("...") %}
            found.setdefault(ast.literal_eval(m.group(1)), str(path))
        source = templatize(raw)
        for m in GETTEXT_CALL.finditer(source):
            found.setdefault(ast.literal_eval(m.group(1)), str(path))
        for m in NGETTEXT_CALL.finditer(source):
            # bentuk jamak: kuncinya "tunggal\0jamak", sama dengan parse_po
            found.setdefault(ast.literal_eval(m.group(1)) + "\0" + ast.literal_eval(m.group(2)), str(path))
    return found


GETTEXT_NAMES = {"_", "_lazy", "gettext", "gettext_lazy", "gettext_noop", "N_"}


def python_msgids():
    """Teks di kode Python yang dibungkus _()/gettext()/gettext_lazy() (selain migrasi & tes)."""
    found = {}
    root = Path(settings.BASE_DIR)
    for path in root.glob("*/**/*.py"):
        rel = path.relative_to(root)
        if rel.parts[0] in ("locale", "static", "media") or "migrations" in rel.parts or rel.name.startswith("tests"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in GETTEXT_NAMES
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, str(rel))
    return found


STORED_CALLS = {
    # fungsi -> argumen berisi teks yang disimpan/ditampilkan apa adanya
    "send": [1, 2], "to_staff": [1, 2], "record": [1, "detail"],
    "order_event": [1, "customer_title", "customer_body", "detail"],
    "booking_event": [1, "customer_title", "customer_body", "detail"],
    "success": [1], "error": [1], "warning": [1], "info": [1],
}
DOMAIN_ERRORS = {"PetshopError", "PosError", "InvalidTransition", "InvalidBookingTransition", "CheckoutError",
                 "InsufficientStock", "PriceChanged"}
STORED_OWNERS = {"send": "Notification", "to_staff": "Notification", "record": "ActivityLog",
                 "success": "messages", "error": "messages", "warning": "messages", "info": "messages"}


def _sample_texts(node):
    """Contoh teks jadi dari literal/f-string: nilai dinamis diganti angka."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "replace":
        return _sample_texts(node.func.value)
    if isinstance(node, ast.IfExp):
        return _sample_texts(node.body) + _sample_texts(node.orelse)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(v.value if isinstance(v, ast.Constant) else "17" for v in node.values)]
    return []


def stored_texts():
    """Teks notifikasi, riwayat aktivitas, dan pesan flash yang ditulis di kode (bukan lewat gettext)."""
    found = {}
    root = Path(settings.BASE_DIR)
    for path in root.glob("*/**/*.py"):
        rel = path.relative_to(root)
        if "migrations" in rel.parts or rel.name.startswith("tests") or rel.name == "seed_demo.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args
                    and ast.unparse(node.exc.func) in DOMAIN_ERRORS):
                # pesan error proses (kasir, booking, kurir) tampil ke pengguna lewat pesan flash/form
                for text in _sample_texts(node.exc.args[0]):
                    found.setdefault(text, f"{rel}:{node.lineno}")
                continue
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in STORED_CALLS:
                continue
            owner = STORED_OWNERS.get(name)
            if owner and not (isinstance(func, ast.Attribute) and ast.unparse(func.value) == owner):
                continue
            args = [node.args[i] for i in STORED_CALLS[name] if isinstance(i, int) and len(node.args) > i]
            args += [kw.value for kw in node.keywords if kw.arg in STORED_CALLS[name]]
            for arg in args:
                for text in _sample_texts(arg):
                    if re.search(r"[a-zA-Z]{3}", text) and text not in ("COD", "Check-in"):
                        found.setdefault(text, f"{rel}:{node.lineno}")
    return found


FORM_MODULES = [
    "account.form", "chatbot.forms", "courier.forms", "customer.forms", "product.form",
    "service.forms", "store.forms", "transaction.form",
]
ERROR_LITERAL = re.compile(r"""(?:ValidationError|add_error)\((?:[^,()]*,\s*)?(?:_\()?("(?:[^"\\]|\\.)+"|'(?:[^'\\]|\\.)+')""")


def form_msgids():
    """Label, bantuan, placeholder, dan pesan error di semua form proyek (diterjemahkan oleh common.form_i18n)."""
    import importlib
    import inspect

    from django import forms
    from django.utils.functional import Promise

    found = {}

    def add(text, where):
        if isinstance(text, Promise):
            with translation.override("en"):
                english = str(text)
            with translation.override("id"):
                text = str(text)
            if english != text:
                return  # sudah punya terjemahan (katalog proyek atau bawaan Django)
        if isinstance(text, str) and text.strip() and re.search(r"[A-Za-z]", text) and not re.fullmatch(r"[a-z0-9_]+", text):
            found.setdefault(text, where)

    for name in FORM_MODULES:
        module = importlib.import_module(name)
        source = inspect.getsource(module)
        for m in ERROR_LITERAL.finditer(source):
            text = ast.literal_eval(m.group(1))
            if "{" not in text:
                add(text, name)
        for cls_name, cls in inspect.getmembers(module, inspect.isclass):
            if not issubclass(cls, forms.BaseForm) or cls.__module__ != name:
                continue
            where = f"{name}.{cls_name}"
            for field in cls.base_fields.values():
                add(field.label, where)
                add(field.help_text, where)
                for key in ("placeholder", "title", "aria-label"):
                    add(field.widget.attrs.get(key), where)
                for message in field.error_messages.values():
                    add(message, where)
    return found


class TranslationCatalogTests(TestCase):
    def test_every_python_gettext_text_has_an_english_translation(self):
        catalog = parse_po(PO_FILE)
        missing = {msgid: where for msgid, where in python_msgids().items() if not catalog.get(msgid)}
        self.assertEqual(missing, {}, "Teks _() di kode Python belum diterjemahkan; tambahkan ke django.po")

    def test_every_form_text_has_an_english_translation(self):
        catalog = parse_po(PO_FILE)
        missing = {msgid: where for msgid, where in form_msgids().items() if not catalog.get(msgid)}
        self.assertEqual(missing, {}, "Label/bantuan/error form belum diterjemahkan; tambahkan ke django.po")

    def test_form_labels_follow_the_active_language(self):
        from store.forms import StoreSettingsForm

        with translation.override("en"):
            self.assertEqual(StoreSettingsForm().fields["tax_percent"].label, "Tax / VAT (%)")
        with translation.override("id"):
            self.assertEqual(StoreSettingsForm().fields["tax_percent"].label, "Pajak / PPN (%)")

    def test_stored_notification_and_activity_texts_have_an_english_translation(self):
        from common.stored_i18n import translate_stored

        with translation.override("en"):
            missing = {t: where for t, where in stored_texts().items() if translate_stored(t) == t}
        self.assertEqual(missing, {})

    def test_stored_texts_are_shown_in_the_viewer_language(self):
        from common.stored_i18n import translate_stored

        with translation.override("en"):
            self.assertEqual(translate_stored("Pesanan #12 dikonfirmasi"), "Order #12 confirmed")
            self.assertEqual(translate_stored("Milo masuk antrean A3"), "Milo joined queue A3")
            self.assertEqual(translate_stored("Titip dari tetangga"), "Titip dari tetangga")
        with translation.override("id"):
            self.assertEqual(translate_stored("Pesanan #12 dikonfirmasi"), "Pesanan #12 dikonfirmasi")
            # istilah bahasa Indonesia diseragamkan: "Order" lama tampil sebagai "Pesanan"
            self.assertEqual(translate_stored("Order #12 sudah dibatalkan."), "Pesanan #12 sudah dibatalkan.")

    def test_counts_use_singular_and_plural_in_english(self):
        from django.template import Context, Template

        tpl = Template("{% load i18n %}{% blocktranslate count n=x %}{{ n }} hewan{% plural %}{{ n }} hewan{% endblocktranslate %}")
        with translation.override("en"):
            self.assertEqual(tpl.render(Context({"x": 1})), "1 pet")
            self.assertEqual(tpl.render(Context({"x": 5})), "5 pets")
        with translation.override("id"):
            self.assertEqual(tpl.render(Context({"x": 5})), "5 hewan")

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
