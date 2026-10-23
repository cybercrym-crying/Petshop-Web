from django.conf import settings
from django.utils import translation


# Bahasa dipilih lewat tombol ID/EN (cookie dari view set_language bawaan Django).
# Sengaja tidak membaca Accept-Language: tanpa pilihan, situs selalu tampil
# dalam Bahasa Indonesia.
class LanguageCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.supported = {code for code, _name in settings.LANGUAGES}

    def __call__(self, request):
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang not in self.supported:
            lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", lang)
        return response
