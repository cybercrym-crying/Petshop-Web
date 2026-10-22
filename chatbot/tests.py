import json

from django.test import TestCase

from account.models import Customer, Role, User

from .models import ChatLog, FaqEntry

# (pertanyaan pelanggan, kata yang harus ada di pertanyaan FAQ yang dipilih)
REALISTIC = [
    ("ongkirnya berapa kak?", "ongkos kirim"),
    ("biaya kirim ke balikpapan brp", "ongkos kirim"),
    ("bisa cod ga?", "pembayaran"),
    ("bayarnya pake apa aja", "pembayaran"),
    ("transfer ke rekening mana", "pembayaran"),
    ("gimana cara order", "memesan"),
    ("cara beli barang di sini", "memesan"),
    ("paket saya sudah sampai mana", "melacak"),
    ("mau cek resi", "melacak"),
    ("mau booking grooming kucing", "booking grooming"),
    ("harga grooming kucing berapa", "harga layanan"),
    ("berapa harga mandi anjing", "harga layanan"),
    ("jam buka grooming", "jam berapa"),
    ("cara batalin pesanan", "membatalkan"),
    ("mau cancel order", "membatalkan"),
    ("lupa pasword", "lupa kata sandi"),
    ("gimana bikin akun", "membuat akun"),
    ("alamat saya salah mau ganti", "alamat pengiriman"),
    ("stok royal canin kosong ya", "stoknya habis"),
    ("nomor wa admin berapa", "menghubungi admin"),
    ("ongkos krim berapa", "ongkos kirim"),  # salah ketik
    ("pembyaran bisa trasfer?", "pembayaran"),  # salah ketik
    # pertanyaan uji tambahan (tidak dipakai saat menyetel kata kunci awal)
    ("kirim ke samarinda kena ongkos ga", "ongkos kirim"),
    ("bisa bayar ditempat?", "pembayaran"),
    ("pesanan saya kok belum datang", "melacak"),
    ("kurirnya dimana sekarang", "melacak"),
    ("mau mandiin kucing", "booking grooming"),
    ("grooming anjing berapaan", "harga layanan"),
    ("salon kucing buka jam brp", "jam berapa"),
    ("saya mau batalin orderan", "membatalkan"),
    ("akun saya ga bisa login", "lupa kata sandi"),
    ("gimana cara daftar member", "membuat akun"),
    ("whiskas ready?", "stoknya habis"),
    ("kapan whiskas ada lagi", "stoknya habis"),
    ("cs nya bisa dihubungi dimana", "menghubungi admin"),
    ("kapan barang dikirim", "melacak"),
]

# Pertanyaan di luar FAQ harus jujur "belum tahu" (bukan dijawab asal).
UNKNOWN = ["jual kandang hamster?", "ada dokter hewan?", "apakah ada promo", "pet hotel ada?"]


class ChatbotTests(TestCase):
    URL = "/chatbot/tanya/"

    def ask(self, **payload):
        r = self.client.post(self.URL, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_default_faq_answers_realistic_questions(self):
        misses = []
        for text, expected in REALISTIC:
            log_count = ChatLog.objects.count()
            data = self.ask(message=text)
            log = ChatLog.objects.order_by("-pk").first()
            matched = log.matched.question.lower() if log and ChatLog.objects.count() > log_count and log.matched else ""
            if expected not in matched:
                misses.append((text, matched or data["answer"][:60]))
        self.assertEqual(misses, [])

    def test_questions_outside_faq_fall_back_instead_of_guessing(self):
        for text in UNKNOWN:
            data = self.ask(message=text)
            self.assertTrue(data["fallback"], text)

    def test_service_prices_filled_from_database(self):
        data = self.ask(message="harga grooming berapa")
        self.assertIn("Mandi Sehat Kucing", data["answer"])
        self.assertIn("Rp 60.000", data["answer"])
        self.assertNotIn("[[layanan]]", data["answer"])

    def test_unknown_question_falls_back_to_whatsapp_and_is_logged(self):
        data = self.ask(message="apakah kalian jual ikan arwana super red")
        self.assertTrue(data["fallback"])
        self.assertIn("wa.me", data["wa"])
        log = ChatLog.objects.get()
        self.assertIsNone(log.matched)

    def test_greeting_and_thanks_are_not_logged(self):
        self.assertIn("Halo", self.ask(message="halo kak")["answer"])
        self.assertIn("Sama-sama", self.ask(message="makasih ya")["answer"])
        self.assertFalse(ChatLog.objects.exists())

    def test_tracking_number_returns_order_status(self):
        from transaction.models import Order

        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        cust = Customer.objects.create(name="Budi", phone_number="0812", address="x")
        order = Order.objects.create(admin=admin, customer=cust, payment_method="TUNAI")
        data = self.ask(message=f"cek pesanan {order.tracking_number.lower().replace('-', ' ')} dong")
        self.assertIn(order.tracking_number, data["answer"])
        self.assertIn("Dikonfirmasi", data["answer"])
        self.assertEqual(data["link"]["url"], f"/lacak/{order.tracking_number}/")
        self.assertNotIn("Budi", data["answer"])  # data pribadi tidak ditampilkan
        data = self.ask(message="resi PS-000000-AAAAAA")
        self.assertIn("tidak ditemukan", data["answer"])

    def test_quick_question_by_id_and_hit_counter(self):
        start = self.client.get("/chatbot/mulai/").json()
        self.assertTrue(start["quick"])
        first = start["quick"][0]
        data = self.ask(faq=first["id"])
        self.assertTrue(data["answer"])
        self.assertEqual(FaqEntry.objects.get(pk=first["id"]).hits, 1)

    def test_inactive_faq_is_ignored(self):
        FaqEntry.objects.filter(question__icontains="ongkos kirim").update(is_active=False)
        data = self.ask(message="ongkir berapa")
        log = ChatLog.objects.get()
        self.assertFalse(log.matched and "ongkos" in log.matched.question.lower())

    def test_bad_payload_does_not_crash(self):
        r = self.client.post(self.URL, data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = self.client.post(self.URL, data=json.dumps(["x"]), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(self.URL).status_code, 405)

    def test_widget_on_storefront_pages(self):
        for url in ("/", "/shop/", "/about/", "/cart", "/checkout", "/layanan/"):
            self.assertContains(self.client.get(url), "data-chatbot", msg_prefix=url)

    def test_admin_manages_faq_and_sees_unanswered(self):
        self.ask(message="apakah ada pet hotel")
        User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.client.login(username="adm", password="x")
        r = self.client.get("/staff/admin/faq/")
        self.assertContains(r, "apakah ada pet hotel")
        self.client.post(
            "/staff/admin/faq/tambah/",
            {
                "question": "Apakah ada penitipan hewan?",
                "answer": "Belum tersedia ya kak.",
                "keywords": "pet hotel, penitipan, titip hewan",
                "order": 5,
                "is_active": "on",
            },
        )
        self.assertTrue(FaqEntry.objects.filter(question="Apakah ada penitipan hewan?").exists())
        self.client.logout()
        data = self.ask(message="ada pet hotel ga?")
        self.assertIn("Belum tersedia", data["answer"])

    def test_link_must_be_internal_or_https(self):
        from .forms import FaqForm

        form = FaqForm({"question": "q", "answer": "a", "order": 1, "link_url": "javascript:alert(1)"})
        self.assertFalse(form.is_valid())

    def test_only_admin_can_open_manage_page(self):
        User.objects.create_user("ksr", password="x", role=Role.CASHIER)
        self.client.login(username="ksr", password="x")
        self.assertEqual(self.client.get("/staff/admin/faq/").status_code, 403)
