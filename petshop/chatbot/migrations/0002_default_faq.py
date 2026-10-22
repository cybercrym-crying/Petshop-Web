"""FAQ awal chatbot. Semua bisa diubah/dihapus admin di menu FAQ Chatbot."""

from django.db import migrations

# (pertanyaan, jawaban, kata kunci, link_url, link_label, pilihan_cepat)
DEFAULT_FAQ = [
    (
        "Bagaimana cara memesan?",
        "Ada dua cara:\n"
        "1. Tanpa akun: masukkan barang ke keranjang, isi data di halaman checkout, lalu pesanan dikirim lewat WhatsApp admin.\n"
        "2. Dengan akun customer: setelah masuk, pesanan langsung tercatat di sistem dan statusnya bisa dipantau di menu Pesanan Saya.",
        "cara pesan, cara order, cara beli, pesan barang, order, beli, checkout, belanja, memesan",
        "/shop/", "Mulai belanja", True,
    ),
    (
        "Metode pembayaran apa saja?",
        "Kami menerima:\n"
        "• Bayar di tempat (COD): bayar tunai ke kurir saat barang sampai.\n"
        "• Transfer bank: admin mengirim nomor rekening lewat WhatsApp, barang dikirim setelah pembayaran lunas.",
        "pembayaran, bayar, metode bayar, cod, bayar di tempat, transfer, rekening, tunai, cash",
        "", "", True,
    ),
    (
        "Berapa ongkos kirimnya?",
        "Ongkos kirim dihitung sesuai alamat dan dikonfirmasi admin setelah pesanan masuk. "
        "Untuk perkiraan, silakan tanya admin di WhatsApp [[wa]].",
        "ongkir, ongkos kirim, biaya kirim, biaya antar, ongkos antar, pengiriman, gratis ongkir",
        "", "", True,
    ),
    (
        "Bagaimana cara melacak pesanan?",
        "Buka halaman Lacak Pesanan lalu masukkan nomor resi (contoh: PS-261022-K7M2QX). "
        "Saat paket diantar, posisi kurir tampil langsung di peta. "
        "Anda juga bisa mengetik nomor resi di chat ini untuk cek status.",
        "lacak, resi, cek pesanan, status pesanan, tracking, track, posisi kurir, pesanan sampai mana, paket, kapan dikirim, kapan sampai, belum datang, belum sampai",
        "/lacak/", "Lacak pesanan", True,
    ),
    (
        "Bagaimana cara booking grooming?",
        "Buka menu Layanan, pilih layanan, isi nama & jenis hewan serta jadwal datang, lalu tekan Buat Booking (perlu akun customer). "
        "Status booking bisa dipantau: Pending → Proses → Selesai.",
        "booking, grooming, mandi, mandiin, potong kuku, perawatan bulu, jadwal grooming, salon, reservasi",
        "/layanan/", "Booking layanan", True,
    ),
    (
        "Berapa harga layanan grooming?",
        "Daftar harga layanan saat ini:\n[[layanan]]\nHarga dapat menyesuaikan kondisi hewan.",
        "harga, harga grooming, harga mandi, harga layanan, tarif, biaya grooming, berapaan, price list, daftar harga, harga potong kuku",
        "/layanan/", "Lihat layanan", True,
    ),
    (
        "Jam berapa layanan grooming buka?",
        "Layanan grooming melayani pukul 08.00–20.00 WITA. Booking online bisa dibuat hingga 60 hari ke depan.",
        "jam buka, jam operasional, buka jam, tutup jam, jam layanan, hari libur, buka hari",
        "", "", False,
    ),
    (
        "Bagaimana cara membatalkan pesanan?",
        "Jika sudah masuk sebagai customer, buka Pesanan Saya lalu tekan Batalkan selama status masih “Menunggu Konfirmasi”. "
        "Jika pesanan sudah dikonfirmasi atau dikirim lewat WhatsApp, hubungi admin di [[wa]].",
        "batal, batalkan, cancel, cancel order, cancel pesanan, batal pesan, membatalkan, pembatalan, refund, uang kembali",
        "/pesanan-saya/", "Pesanan Saya", False,
    ),
    (
        "Bagaimana cara membuat akun?",
        "Tekan ikon orang di pojok kanan atas lalu pilih Daftar akun customer. Isi nama, nama pengguna, nomor WhatsApp, alamat, dan kata sandi.",
        "daftar, registrasi, register, buat akun, bikin akun, akun baru, sign up",
        "/daftar", "Daftar sekarang", False,
    ),
    (
        "Saya lupa kata sandi, bagaimana?",
        "Untuk keamanan, reset kata sandi dibantu admin. Hubungi admin lewat WhatsApp [[wa]] dengan menyebutkan nama pengguna dan nomor HP akun Anda.",
        "lupa password, lupa kata sandi, reset password, login, tidak bisa login, ga bisa login, tidak bisa masuk, gagal login, gagal masuk, ganti password",
        "", "", False,
    ),
    (
        "Bagaimana cara mengubah alamat pengiriman?",
        "Alamat bisa diubah di halaman checkout (untuk customer yang sudah masuk) dan otomatis tersimpan sebagai alamat utama akun. "
        "Untuk pesanan yang sudah dibuat, hubungi admin di [[wa]].",
        "ubah alamat, ganti alamat, alamat salah, alamat pengiriman, pindah alamat",
        "", "", False,
    ),
    (
        "Barang yang saya cari stoknya habis?",
        "Stok di situs selalu diperbarui. Jika barang habis, simpan ke Favorit (ikon hati) atau tanyakan perkiraan restok ke admin di [[wa]].",
        "stok habis, restock, restok, kosong, ready, tersedia, ready stock, kapan ada, ada lagi, kapan ready, habis",
        "/favorit/", "Lihat favorit", False,
    ),
    (
        "Bagaimana menghubungi admin?",
        "Admin bisa dihubungi lewat WhatsApp [[wa]]. Tekan tombol Chat admin di bawah untuk langsung membuka WhatsApp.",
        "hubungi, kontak, contact, admin, cs, customer service, whatsapp, wa, nomor telepon, telepon",
        "", "", False,
    ),
]


def add_faq(apps, schema_editor):
    FaqEntry = apps.get_model("chatbot", "FaqEntry")
    for order, (question, answer, keywords, url, label, quick) in enumerate(DEFAULT_FAQ, start=1):
        FaqEntry.objects.get_or_create(
            question=question,
            defaults={
                "answer": answer,
                "keywords": keywords,
                "link_url": url,
                "link_label": label,
                "is_quick": quick,
                "order": order * 10,
            },
        )


def remove_faq(apps, schema_editor):
    FaqEntry = apps.get_model("chatbot", "FaqEntry")
    FaqEntry.objects.filter(question__in=[row[0] for row in DEFAULT_FAQ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_faq, remove_faq),
    ]
