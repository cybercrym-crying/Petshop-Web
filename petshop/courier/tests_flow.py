"""Tahap 3: scan ambil paket, rute terdekat->terjauh, kunci GPS, serah terima QR + foto, setoran COD."""

import io
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from account.models import Role, User
from store.models import ActivityLog, Notification, StoreSettings
from transaction.models import Order, OrderStatus, PaymentStatus
from transaction.tests import make_product

from . import routing
from .models import CashRemittance, CourierLocation, RemittanceStatus

STORE = (-1.2654, 116.8312)


def photo():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(buf, "JPEG")
    return SimpleUploadedFile("serah.jpg", buf.getvalue(), content_type="image/jpeg")


class RoutingTests(TestCase):
    def test_nearest_first_then_two_opt(self):
        pts = [(-1.2654, 116.90, "jauh"), (-1.2654, 116.84, "dekat"), (-1.2654, 116.87, "tengah")]
        self.assertEqual([p[2] for p in routing.plan(STORE, pts)], ["dekat", "tengah", "jauh"])

    def test_two_opt_never_longer_than_nearest_neighbour(self):
        import random

        rng = random.Random(4)
        for _ in range(20):
            pts = [(STORE[0] + rng.uniform(-0.08, 0.08), STORE[1] + rng.uniform(-0.08, 0.08), n) for n in range(8)]
            nn = routing.nearest_neighbour(STORE, pts)
            best = routing.plan(STORE, pts)
            self.assertLessEqual(routing.path_length(STORE, best), routing.path_length(STORE, nn) + 1e-9)
            self.assertEqual(sorted(p[2] for p in best), list(range(8)))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="petshop-test-media-"))
class CourierFlowTests(TestCase):
    def setUp(self):
        self.courier = User.objects.create_user("kur", password="Pass12345!x", role=Role.COURIER, phone_number="081344440000")
        self.cashier = User.objects.create_user("kas", password="Pass12345!x", role=Role.CASHIER, phone_number="081344441111")
        self.customer = User.objects.create_user(
            "cus", password="Pass12345!x", role=Role.CUSTOMER, phone_number="081344442222", address="Jl. C"
        )
        self.product = make_product("Whiskas", stock=50)
        self.client.force_login(self.courier)

    def order(self, lng="116.871200", method="TUNAI"):
        order = Order.place_online(self.customer, [(self.product.pk, 1)], method, location=("-1.265400", lng))
        order.confirm(self.cashier)
        if method == "TRANSFER":
            order.verify_payment(self.cashier)
        return order

    def gps(self, lat="-1.265400", lng="116.831200"):
        return self.client.post(reverse("courier:share_location"), {"lat": lat, "lng": lng, "accuracy": 8})

    def pickup(self, order):
        return self.client.post(reverse("courier:pickup"), {"code": order.tracking_number}, follow=True)

    def test_pickup_list_links_only_own_orders(self):
        mine, other = self.order(), self.order()
        mine.assign_courier(self.courier)
        r = self.client.get(reverse("courier:pickup"))
        self.assertContains(r, reverse("courier:order_detail", args=[mine.pk]))
        self.assertNotContains(r, reverse("courier:order_detail", args=[other.pk]))
        self.assertContains(r, f"#{other.pk} ")

    def test_pickup_requires_fresh_gps(self):
        order = self.order()
        r = self.pickup(order)
        self.assertContains(r, "GPS Anda belum aktif")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        CourierLocation.objects.create(
            courier=self.courier, latitude=Decimal("-1.2654"), longitude=Decimal("116.8312"),
            recorded_at=timezone.now() - timedelta(minutes=10),
        )
        r = self.pickup(order)
        self.assertContains(r, "GPS Anda belum aktif")  # lokasi terlalu lama = GPS mati

    def test_pickup_scan_starts_delivery_and_notifies(self):
        self.gps()
        order = self.order()
        r = self.pickup(order)
        self.assertContains(r, "masuk rute Anda")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ON_DELIVERY)
        self.assertEqual(order.courier, self.courier)
        self.assertEqual(order.route_position, 1)
        self.assertIsNotNone(order.packed_at)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="dibawa kurir").exists())
        self.assertTrue(ActivityLog.for_object(order).filter(action="Diambil kurir").exists())

    def test_cannot_pickup_unpaid_transfer_or_other_couriers_package(self):
        self.gps()
        unpaid = Order.place_online(self.customer, [(self.product.pk, 1)], "TRANSFER", location=("-1.265400", "116.84"))
        unpaid.confirm(self.cashier)
        self.assertContains(self.pickup(unpaid), "belum siap dikirim")
        other = User.objects.create_user("kur2", password="x", role=Role.COURIER, phone_number="081344443333")
        mine = self.order()
        mine.assign_courier(other)
        self.assertContains(self.pickup(mine), "kurir lain")

    def test_max_packages_per_courier(self):
        store = StoreSettings.current()
        store.max_packages_per_courier = 1
        store.save()
        self.gps()
        self.pickup(self.order())
        self.assertContains(self.pickup(self.order()), "maks. 1")

    def test_route_orders_nearest_first(self):
        self.gps()
        far, near = self.order(lng="116.900000"), self.order(lng="116.840000")
        self.pickup(far)
        self.pickup(near)
        near.refresh_from_db()
        far.refresh_from_db()
        self.assertEqual((near.route_position, far.route_position), (1, 2))
        r = self.client.get(reverse("courier:dashboard"))
        self.assertEqual(r.context["next_stop"].pk, near.pk)
        self.assertContains(r, "Tujuan berikutnya")
        data = self.client.get(reverse("courier:route_data")).json()
        self.assertEqual([s["id"] for s in data["stops"]], [near.pk, far.pk])
        # pelanggan order jauh melihat 1 pengantaran sebelum dia
        self.assertEqual(far.stops_before(), 1)

    def test_customer_sees_eta_and_stops_on_live_map(self):
        self.gps()
        far, near = self.order(lng="116.900000"), self.order(lng="116.840000")
        self.pickup(far)
        self.pickup(near)
        # Ping berikutnya setelah paket diambil (ping sebelumnya kena batas 5 detik).
        CourierLocation.objects.create(
            courier=self.courier, latitude=Decimal("-1.265400"),
            longitude=Decimal("116.835000"), recorded_at=timezone.now(),
        )
        self.client.force_login(self.customer)
        data = self.client.get(reverse("customer:track_location", args=[far.tracking_number])).json()
        self.assertEqual(data["stops_before"], 1)
        self.assertIn("eta_minutes", data)
        self.assertIn("destination", data)
        dash = self.client.get(reverse("customer:dashboard"))
        self.assertContains(dash, "data-track-live")
        self.assertContains(dash, "QR serah-terima")

    def handover(self, order, code=None, **extra):
        return self.client.post(
            reverse("courier:handover", args=[order.pk]),
            {"code": code if code is not None else order.handover_payload, "photo": photo(),
             "latitude": "-1.265400", "longitude": "116.871200", **extra},
            follow=True,
        )

    def test_handover_with_customer_qr_and_photo_marks_delivered(self):
        self.gps()
        order = self.order(method="TRANSFER")
        self.pickup(order)
        check = self.client.post(reverse("courier:check_handover", args=[order.pk]), {"code": "SALAH123"})
        self.assertEqual(check.status_code, 400)
        check = self.client.post(reverse("courier:check_handover", args=[order.pk]), {"code": order.handover_payload})
        self.assertTrue(check.json()["ok"])
        r = self.handover(order)
        self.assertContains(r, "selesai diantar")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)
        self.assertTrue(order.handover_verified)
        self.assertTrue(order.delivery_photo)
        self.assertEqual(order.delivered_latitude, Decimal("-1.265400"))
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="sudah diterima").exists())

    def test_handover_rejects_wrong_code_and_label_resi(self):
        self.gps()
        order = self.order(method="TRANSFER")
        self.pickup(order)
        self.assertContains(self.handover(order, code="ZZZZZZZZ"), "tidak cocok")
        # QR label (resi) bukan bukti penerima ada di tempat
        self.assertContains(self.handover(order, code=order.tracking_number), "tidak cocok")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ON_DELIVERY)

    def test_handover_accepts_spoken_code(self):
        self.gps()
        order = self.order(method="TRANSFER")
        self.pickup(order)
        self.handover(order, code=order.handover_code.lower())
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)

    def test_handover_requires_photo(self):
        self.gps()
        order = self.order(method="TRANSFER")
        self.pickup(order)
        self.client.post(reverse("courier:handover", args=[order.pk]), {"code": order.handover_payload})
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ON_DELIVERY)

    def test_cod_cash_flow_to_cashier(self):
        self.gps()
        a, b = self.order(), self.order(lng="116.85")
        self.pickup(a)
        self.pickup(b)
        self.assertContains(self.handover(a), "Pastikan uang tunai")  # belum centang uang diterima
        self.handover(a, cash_received="1")
        self.handover(b, cash_received="1")
        a.refresh_from_db()
        self.assertEqual(a.payment_status, PaymentStatus.PAID)
        self.assertEqual(a.cash_collected, a.total_payment)
        r = self.client.get(reverse("courier:cash"))
        self.assertEqual(r.context["on_hand_total"], a.total_payment + b.total_payment)
        self.client.post(reverse("courier:cash"))
        remit = CashRemittance.objects.get()
        self.assertEqual(remit.amount, a.total_payment + b.total_payment)
        self.assertFalse(Order.cash_on_hand(self.courier).exists())
        self.client.force_login(self.cashier)
        r = self.client.post(reverse("transaction:remittances"), {"remittance": remit.pk, "received_amount": remit.amount - 1000})
        remit.refresh_from_db()
        self.assertEqual(remit.status, RemittanceStatus.SUBMITTED)  # selisih wajib dicatat
        self.client.post(reverse("transaction:remittances"), {"remittance": remit.pk, "received_amount": remit.amount - 1000, "note": "kurang 1.000"})
        remit.refresh_from_db()
        self.assertEqual(remit.status, RemittanceStatus.RECEIVED)
        self.assertEqual(remit.difference, -1000)

    def test_problem_returns_package_to_store(self):
        self.gps()
        order = self.order()
        self.pickup(order)
        r = self.client.post(reverse("courier:problem", args=[order.pk]), {"note": "Penerima tidak ada di lokasi"}, follow=True)
        self.assertContains(r, "kembali ke toko")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertIsNone(order.courier)
        self.assertTrue(Notification.objects.filter(user=self.cashier, title__contains="gagal diantar").exists())

    def test_courier_cannot_handover_others_package(self):
        self.gps()
        order = self.order()
        self.pickup(order)
        other = User.objects.create_user("kur3", password="x", role=Role.COURIER, phone_number="081344445555")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("courier:handover", args=[order.pk])).status_code, 404)
