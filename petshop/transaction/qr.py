"""QR code SVG (dibuat di server, tanpa layanan luar)."""

import qrcode
import qrcode.image.svg
from django.http import HttpResponse


def qr_svg(text):
    image = qrcode.make(
        text,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=10,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    return image.to_string(encoding="unicode")


def qr_response(text):
    response = HttpResponse(qr_svg(text), content_type="image/svg+xml")
    response["Cache-Control"] = "private, max-age=3600"
    return response
