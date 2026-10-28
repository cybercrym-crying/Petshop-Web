"""Label, teks bantuan, placeholder, dan pesan error form ikut bahasa ID/EN yang aktif.

Label form proyek ini ditulis sebagai teks Indonesia biasa (verbose_name model dan
label=... di form), jadi tidak lewat gettext. Daripada membungkus ratusan teks satu per
satu (dan membuat migrasi baru untuk setiap verbose_name), semua form diterjemahkan di
satu tempat saat dibuat dan saat divalidasi. Teks yang belum ada di katalog tampil apa
adanya (bahasa Indonesia), jadi aman.
"""

from django import forms
from django.forms.utils import ErrorList
from django.utils.translation import gettext

from common.stored_i18n import translate_stored

_installed = False


def _tr(text):
    return gettext(str(text)) if text else text


def translate_fields(form):
    for field in form.fields.values():
        if field.label:
            field.label = _tr(field.label)
        if field.help_text:
            field.help_text = _tr(field.help_text)
        attrs = getattr(field.widget, "attrs", {})
        for key in ("placeholder", "title", "aria-label"):
            if attrs.get(key):
                attrs[key] = _tr(attrs[key])
        if field.error_messages:
            field.error_messages = {k: _tr(v) for k, v in field.error_messages.items()}


def translate_errors(form):
    for name, errors in list(form._errors.items()):
        translated = ErrorList(error_class=errors.error_class, renderer=errors.renderer)
        for error in errors.as_data():
            for message in error.messages:
                # pesan dari model/proses (mis. "Order #12 sudah dibatalkan.") memakai pola katalog
                translated.append(translate_stored(_tr(message)))
        form._errors[name] = translated


def install():
    global _installed
    if _installed:
        return
    _installed = True
    original_init = forms.BaseForm.__init__
    original_full_clean = forms.BaseForm.full_clean

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        translate_fields(self)

    def full_clean(self):
        original_full_clean(self)
        if getattr(self, "_errors", None):
            translate_errors(self)

    forms.BaseForm.__init__ = __init__
    forms.BaseForm.full_clean = full_clean
