"""Alasan pembatalan pesanan & booking: pilihan cepat per pihak + isian bebas.

Pelanggan, admin, dan kasir wajib menyebut alasan setiap kali membatalkan;
alasannya disimpan di pesanan/booking dan ditampilkan ke kedua pihak.
"""
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from common.exceptions import PetshopError

OTHER = "lain"
MIN_LENGTH = 3

REASONS = {
    "customer_order": [
        _lazy("Salah pilih produk atau jumlah"),
        _lazy("Ingin ganti alamat atau cara bayar"),
        _lazy("Barang sudah tidak dibutuhkan"),
        _lazy("Waktu pengiriman terlalu lama"),
    ],
    "customer_booking": [
        _lazy("Jadwal bentrok atau berhalangan"),
        _lazy("Hewan sedang sakit"),
        _lazy("Ingin ganti layanan atau jadwal"),
        _lazy("Sudah tidak membutuhkan layanan"),
    ],
    "staff_order": [
        _lazy("Stok habis"),
        _lazy("Pelanggan minta dibatalkan"),
        _lazy("Pembayaran tidak diterima"),
        _lazy("Alamat di luar jangkauan antar"),
    ],
    "staff_booking": [
        _lazy("Pelanggan minta dibatalkan"),
        _lazy("Groomer tidak tersedia"),
        _lazy("Jadwal penuh atau toko tutup"),
        _lazy("Pelanggan tidak bisa dihubungi"),
    ],
}


class MissingCancelReason(PetshopError):
    pass


def read_cancel_reason(post):
    """Ambil alasan dari form (`reason_choice` + `reason_note`). Galat bila kosong."""
    choice = (post.get("reason_choice") or "").strip()
    note = " ".join((post.get("reason_note") or "").split())
    if choice and choice != OTHER:
        reason = f"{choice}: {note}" if note else choice
    else:
        reason = note
    if len(reason) < MIN_LENGTH:
        raise MissingCancelReason(_("Pilih atau tulis alasan pembatalan."))
    return reason[:255]
