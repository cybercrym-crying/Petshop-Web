from django.contrib.messages.storage.fallback import FallbackStorage

from common.stored_i18n import translate_stored


class TranslatedFallbackStorage(FallbackStorage):
    """Pesan flash yang ditulis sebagai teks Indonesia ikut bahasa aktif pengguna."""

    def add(self, level, message, extra_tags=""):
        if isinstance(message, str):
            message = translate_stored(message)
        return super().add(level, message, extra_tags)
