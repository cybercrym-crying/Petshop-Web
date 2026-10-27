"""Tahap 2: ongkir, bukti transfer via kamera, validasi kasir, batas bayar, packing, label & QR."""

import io
from datetime import timedelta
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from account.models import Role, User
from store.models import ActivityLog, Notification

from .models import Order, OrderStatus, PaymentStatus
from .tests import make_product


def photo(name="bukti.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT="/tmp/petshop-test-media")
class TransferFlowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            "cus", password="Pass12345!x", role=Role.CUSTOMER, phone_number="081311112222", address="Jl. A"
        )
        self.cashier = User.objects.create_user("kas", password="Pass12345!x", role=Role.CASHIER, phone_number="081311113333")
        self.product = make_product("Whiskas", stock=10)
        self.order = Order.place_online(
            self.customer, [(self.product.pk, 2)], "TRANSFER", location=("-1.265400", "116.831200")
        )

    def test_transfer_gets_deadline_and_shipping(self):
        self.assertIsNotNone(self.order.payment_due_at)
        hours = (self.order.payment_due_at - timezone.now()).total_seconds() / 3600
        self.assertAlmostEqual(hours, 1, delta=0.1)  # batas bayar transfer/QRIS 1 jam
        self.assertEqual(self.order.shipping_fee, 5000)

    def upload(self):
        self.client.login(username="cus", password="Pass12345!x")
        return self.client.post(reverse("customer:payment_proof", args=[self.order.pk]), {"photo": photo()})

    def test_customer_uploads_proof_and_staff_is_notified(self):
        r = self.upload()
        self.assertRedirects(r, reverse("customer:dashboard"), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertTrue(self.order.awaiting_payment_check)
        self.assertTrue(Notification.objects.filter(user=self.cashier).exists())
        self.assertTrue(ActivityLog.for_object(self.order).filter(action="Bukti transfer dikirim").exists())

    def test_proof_page_has_camera(self):
        self.client.login(username="cus", password="Pass12345!x")
        r = self.client.get(reverse("customer:payment_proof", args=[self.order.pk]))
        self.assertContains(r, "data-camera")
        self.assertContains(r, "camera.js")

    def test_other_customer_cannot_upload(self):
        User.objects.create_user("cus2", password="Pass12345!x", role=Role.CUSTOMER, phone_number="081399990000")
        self.client.login(username="cus2", password="Pass12345!x")
        r = self.client.post(reverse("customer:payment_proof", args=[self.order.pk]), {"photo": photo()})
        self.assertEqual(r.status_code, 404)

    def test_non_image_rejected(self):
        self.client.login(username="cus", password="Pass12345!x")
        bad = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        r = self.client.post(reverse("customer:payment_proof", args=[self.order.pk]), {"photo": bad})
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertFalse(self.order.payment_proof)

    def test_cashier_approves(self):
        self.upload()
        self.order.confirm(self.cashier)
        self.client.login(username="kas", password="Pass12345!x")
        r = self.client.get(reverse("transaction:payment_check", args=[self.order.pk]))
        self.assertContains(r, "Setujui pembayaran")
        self.client.post(reverse("transaction:payment_check", args=[self.order.pk]), {"decision": "approve"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)
        self.assertEqual(self.order.payment_verified_by, self.cashier)
        self.assertEqual(self.order.packing_seq, 1)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="diterima").exists())

    def test_cashier_rejects_with_reason(self):
        self.upload()
        self.client.login(username="kas", password="Pass12345!x")
        r = self.client.post(reverse("transaction:payment_check", args=[self.order.pk]), {"decision": "reject", "note": ""})
        self.order.refresh_from_db()
        self.assertTrue(self.order.awaiting_payment_check)  # alasan wajib
        self.client.post(reverse("transaction:payment_check", args=[self.order.pk]), {"decision": "reject", "note": "Nominal kurang"})
        self.order.refresh_from_db()
        self.assertFalse(self.order.payment_proof)
        self.assertEqual(self.order.payment_reject_note, "Nominal kurang")
        self.assertTrue(self.order.can_upload_proof)

    def test_courier_cannot_open_payment_check(self):
        User.objects.create_user("kur", password="Pass12345!x", role=Role.COURIER, phone_number="081311114444")
        self.client.login(username="kur", password="Pass12345!x")
        self.assertEqual(self.client.get(reverse("transaction:payment_check", args=[self.order.pk])).status_code, 403)

    def test_expired_transfer_is_cancelled_and_stock_returned(self):
        Order.objects.filter(pk=self.order.pk).update(payment_due_at=timezone.now() - timedelta(minutes=1))
        out = StringIO()
        call_command("cancel_expired_orders", stdout=out)
        self.assertIn("1 pesanan", out.getvalue())
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="dibatalkan").exists())

    def test_expired_but_proof_sent_is_kept(self):
        self.upload()
        Order.objects.filter(pk=self.order.pk).update(payment_due_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(Order.cancel_expired(), 0)

    def test_manage_page_triggers_auto_cancel(self):
        Order.objects.filter(pk=self.order.pk).update(payment_due_at=timezone.now() - timedelta(minutes=1))
        self.client.login(username="kas", password="Pass12345!x")
        self.client.get(reverse("transaction:manage_transaction"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CANCELLED)


@override_settings(MEDIA_ROOT="/tmp/petshop-test-media")
class PackingAndLabelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            "cus", password="Pass12345!x", role=Role.CUSTOMER, phone_number="081322221111", address="Jl. B"
        )
        self.cashier = User.objects.create_user("kas", password="Pass12345!x", role=Role.CASHIER, phone_number="081322223333")
        self.product = make_product("Pasir", stock=20)

    def cod(self):
        order = Order.place_online(self.customer, [(self.product.pk, 1)], "TUNAI", location=("-1.265400", "116.831200"))
        order.confirm(self.cashier)
        return order

    def test_packing_numbers_are_daily_sequence(self):
        a, b = self.cod(), self.cod()
        self.assertEqual((a.packing_seq, b.packing_seq), (1, 2))
        self.assertEqual(b.packing_label, "002")
        self.assertEqual(a.packing_date, timezone.localdate())

    def test_unpaid_transfer_gets_no_packing_number(self):
        order = Order.place_online(self.customer, [(self.product.pk, 1)], "TRANSFER", location=("-1.265400", "116.831200"))
        order.confirm(self.cashier)
        self.assertIsNone(order.packing_seq)

    def test_packing_queue_and_mark_packed(self):
        order = self.cod()
        self.client.login(username="kas", password="Pass12345!x")
        r = self.client.get(reverse("transaction:packing_queue"))
        self.assertContains(r, f"Order #{order.pk}")
        self.client.post(reverse("transaction:update_status", args=[order.pk]), {"action": "packed", "next": "packing"})
        order.refresh_from_db()
        self.assertIsNotNone(order.packed_at)
        self.assertEqual(order.packed_by, self.cashier)

    def test_label_has_qr_and_cod_amount(self):
        order = self.cod()
        self.client.login(username="kas", password="Pass12345!x")
        r = self.client.get(reverse("transaction:print_label", args=[order.pk]))
        self.assertContains(r, order.tracking_number)
        self.assertContains(r, "COD Rp")
        self.assertContains(r, reverse("transaction:label_qr", args=[order.pk]))
        qr = self.client.get(reverse("transaction:label_qr", args=[order.pk]))
        self.assertEqual(qr["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", qr.content)

    def test_handover_qr_only_for_owner(self):
        order = self.cod()
        self.assertEqual(len(order.handover_code), 8)
        self.client.login(username="cus", password="Pass12345!x")
        self.assertEqual(self.client.get(reverse("customer:handover_qr", args=[order.pk])).status_code, 200)
        User.objects.create_user("cus2", password="Pass12345!x", role=Role.CUSTOMER, phone_number="081322229999")
        self.client.login(username="cus2", password="Pass12345!x")
        self.assertEqual(self.client.get(reverse("customer:handover_qr", args=[order.pk])).status_code, 404)

    def test_track_location_hides_destination_from_strangers(self):
        order = self.cod()
        self.client.post(reverse("customer:track_detail", args=[order.tracking_number]), {"wa4": order.phone_last4})
        r = self.client.get(reverse("customer:track_location", args=[order.tracking_number]))
        self.assertNotIn("destination", r.json())
