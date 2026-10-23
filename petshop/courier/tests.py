import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from account.models import Customer, Role, User
from transaction.models import Order, OrderStatus


def make_photo(name="bukti.jpg", fmt="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "green").save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def make_courier(username):
    return User.objects.create_user(username, password="x", role=Role.COURIER)


def make_order(courier, status):
    admin = User.objects.get_or_create(
        username="admin_board", defaults={"role": Role.ADMIN}
    )[0]
    customer, _ = Customer.objects.get_or_create(
        phone_number="0811", defaults={"name": "Budi", "address": "Jl. Mawar 1"}
    )
    return Order.objects.create(
        admin=admin,
        courier=courier,
        customer=customer,
        order_status=status,
        payment_method="TUNAI",
    )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="petshop-test-media-"))
class CourierPackagesTests(TestCase):
    """Daftar paket per status (tanpa tombol ubah status; ambil & serah lewat scan QR)."""

    def setUp(self):
        self.courier = make_courier("kurir_a")
        self.client.force_login(self.courier)
        self.url = reverse("courier:packages")

    def test_counts_are_split_by_status(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        r = self.client.get(self.url)
        self.assertEqual(r.context["total_on_delivery"], 1)
        self.assertEqual(r.context["total_delivered"], 1)

    def test_on_delivery_card_links_to_qr_handover(self):
        order = make_order(self.courier, OrderStatus.ON_DELIVERY)
        r = self.client.get(self.url, {"status": "on_delivery"})
        self.assertContains(r, reverse("courier:handover", args=[order.pk]))
        self.assertNotContains(r, "Mulai Kirim")

    def test_history_lists_finished_orders_as_tappable_rows(self):
        done = make_order(self.courier, OrderStatus.DELIVERED)
        make_order(make_courier("lain"), OrderStatus.DELIVERED)
        r = self.client.get(reverse("courier:history"))
        self.assertContains(r, 'class="hist-row"', count=1)
        self.assertContains(r, reverse("courier:order_detail", args=[done.pk]))

    def test_unknown_status_falls_back_to_pending(self):
        r = self.client.get(self.url, {"status": "aneh"})
        self.assertEqual(r.context["current"], "pending")

    def test_other_couriers_orders_are_not_shown(self):
        other = make_courier("kurir_b")
        make_order(other, OrderStatus.ON_DELIVERY)
        r = self.client.get(self.url, {"status": "on_delivery"})
        self.assertEqual(r.context["total_on_delivery"], 0)

    def test_old_status_buttons_are_gone(self):
        self.assertFalse(any(p.name == "update_status" for p in __import__("courier.urls").urls.urlpatterns))

    def test_every_courier_page_has_gps_lock(self):
        order = make_order(self.courier, OrderStatus.ON_DELIVERY)
        for url in (
            reverse("courier:dashboard"), self.url, reverse("courier:pickup"), reverse("courier:cash"),
            reverse("courier:history"), reverse("courier:order_detail", args=[order.pk]),
            reverse("courier:handover", args=[order.pk]), reverse("courier:problem", args=[order.pk]),
        ):
            r = self.client.get(url)
            self.assertContains(r, "data-gps-lock", msg_prefix=url)
            self.assertContains(r, "gps_guard.js", msg_prefix=url)


class LiveLocationTests(TestCase):
    URL = "/staff/courier/lokasi/"

    def setUp(self):
        self.courier = make_courier("kurir_gps")
        self.client.login(username="kurir_gps", password="x")

    def ping(self, lat="-1.265400", lng="116.831200", accuracy="12"):
        return self.client.post(self.URL, {"lat": lat, "lng": lng, "accuracy": accuracy})

    def test_saved_even_without_delivery_for_gps_lock(self):
        from courier.models import CourierLocation

        r = self.ping()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(CourierLocation.is_fresh(self.courier))

    def test_saved_while_delivering_and_shown_on_tracking_page(self):
        from courier.models import CourierLocation

        order = make_order(self.courier, OrderStatus.CONFIRMED)
        order.mark_on_delivery(self.courier)
        r = self.ping()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["saved"])
        self.assertEqual(CourierLocation.objects.count(), 1)
        # kiriman terlalu rapat diabaikan
        self.assertFalse(self.ping().json()["saved"])

        self.client.logout()
        url = reverse("customer:track_location", args=[order.tracking_number])
        data = self.client.get(url).json()
        self.assertTrue(data["live"])
        self.assertAlmostEqual(data["last"]["lat"], -1.2654)
        self.assertEqual(len(data["points"]), 1)
        page = self.client.get(reverse("customer:track_detail", args=[order.tracking_number]))
        self.assertContains(page, "data-track-live")
        self.assertContains(page, "leaflet")

    def test_location_hidden_after_delivered(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        order.mark_on_delivery(self.courier)
        self.ping()
        order.mark_delivered()
        data = self.client.get(
            reverse("customer:track_location", args=[order.tracking_number])
        ).json()
        self.assertFalse(data["live"])
        self.assertEqual(data["points"], [])

    def test_invalid_coordinates_and_other_roles(self):
        self.assertEqual(self.ping(lat="200").status_code, 400)
        self.assertEqual(self.ping(lng="abc").status_code, 400)
        User.objects.create_user("adm_gps", password="x", role=Role.ADMIN)
        self.client.login(username="adm_gps", password="x")
        self.assertEqual(self.ping().status_code, 403)

    def test_old_order_without_shipped_at_still_shows_location(self):
        order = make_order(self.courier, OrderStatus.ON_DELIVERY)  # shipped_at kosong
        self.assertIsNone(order.shipped_at)
        self.ping()
        data = self.client.get(
            reverse("customer:track_location", args=[order.tracking_number])
        ).json()
        self.assertTrue(data["live"])
