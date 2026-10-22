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
class CourierBoardTests(TestCase):
    def setUp(self):
        self.courier = make_courier("kurir_a")
        self.client.force_login(self.courier)
        self.url = reverse("courier:dashboard")

    def test_counts_are_split_by_status(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        response = self.client.get(self.url)
        self.assertEqual(response.context["total_pending"], 2)
        self.assertEqual(response.context["total_on_delivery"], 1)
        self.assertEqual(response.context["total_delivered"], 1)

    def test_default_list_is_pending_only(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        response = self.client.get(self.url)
        self.assertEqual(response.context["current"], "pending")
        self.assertEqual(len(response.context["current_orders"]), 1)
        self.assertEqual(
            response.context["current_orders"][0].order_status, OrderStatus.CONFIRMED
        )

    def test_each_status_shows_only_its_own_orders(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        expected = {"pending": 1, "on_delivery": 2, "done": 1}
        for status, count in expected.items():
            response = self.client.get(self.url, {"status": status})
            self.assertEqual(response.context["current"], status)
            self.assertEqual(len(response.context["current_orders"]), count)

    def test_unknown_status_falls_back_to_pending(self):
        response = self.client.get(self.url, {"status": "apa-saja"})
        self.assertEqual(response.context["current"], "pending")

    def test_done_list_is_limited_and_links_to_history(self):
        for _ in range(12):
            make_order(self.courier, OrderStatus.DELIVERED)
        response = self.client.get(self.url, {"status": "done"})
        self.assertEqual(len(response.context["current_orders"]), response.context["done_limit"])
        self.assertEqual(response.context["total_delivered"], 12)
        self.assertContains(response, "Lihat semua riwayat")

    def test_other_couriers_orders_are_not_shown(self):
        other = make_courier("kurir_b")
        make_order(other, OrderStatus.CONFIRMED)
        response = self.client.get(self.url)
        self.assertEqual(response.context["total_pending"], 0)

    def test_stat_boxes_link_to_each_status(self):
        response = self.client.get(self.url)
        for status in ("pending", "on_delivery", "done"):
            self.assertContains(response, f"?status={status}")

    def test_card_button_matches_the_status(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        pending = self.client.get(self.url, {"status": "pending"})
        self.assertContains(pending, "Mulai Kirim")
        self.assertNotContains(pending, "Selesaikan")
        on_delivery = self.client.get(self.url, {"status": "on_delivery"})
        self.assertContains(on_delivery, "Selesaikan")
        self.assertNotContains(on_delivery, "Mulai Kirim")

    def test_start_and_finish_delivery(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        url = reverse("courier:update_status", args=[order.pk])
        self.client.post(url, {"action": "on_delivery", "status": "pending"})
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ON_DELIVERY)
        self.client.post(
            url, {"action": "delivered", "status": "on_delivery", "photo": make_photo()}
        )
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)

    def test_action_returns_to_the_list_it_came_from(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery", "status": "pending"},
        )
        self.assertRedirects(response, f"{self.url}?status=pending")

    def test_return_status_is_whitelisted(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery", "status": "https://contoh.com"},
        )
        self.assertRedirects(response, f"{self.url}?status=pending")

    def test_repeated_action_shows_message_instead_of_error(self):
        order = make_order(self.courier, OrderStatus.DELIVERED)
        url = reverse("courier:update_status", args=[order.pk])
        response = self.client.post(url, {"action": "on_delivery"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tidak bisa diubah")

    def test_courier_cannot_update_someone_elses_order(self):
        other = make_courier("kurir_c")
        order = make_order(other, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]), {"action": "on_delivery"}
        )
        self.assertEqual(response.status_code, 404)

    def test_success_message_is_shown_once(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery", "status": "pending"},
            follow=True,
        )
        self.assertContains(response, f"Order #{order.pk} sedang dikirim.", count=1)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="petshop-test-media-"))
class DeliveryProofTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.courier = make_courier("kurir_bukti")
        self.client.force_login(self.courier)
        self.order = make_order(self.courier, OrderStatus.ON_DELIVERY)
        self.url = reverse("courier:update_status", args=[self.order.pk])

    def finish(self, **data):
        return self.client.post(self.url, {"action": "delivered", **data})

    def test_finish_with_photo_stores_proof_and_times(self):
        self.finish(photo=make_photo(), note="Diterima satpam")
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.DELIVERED)
        self.assertTrue(self.order.delivery_photo)
        self.assertTrue(self.order.delivery_photo.name.startswith("delivery_proofs/"))
        self.assertNotIn("bukti", self.order.delivery_photo.name)  # nama diacak
        self.assertEqual(self.order.delivery_note, "Diterima satpam")
        self.assertIsNotNone(self.order.delivered_at)

    def test_finish_without_photo_is_rejected(self):
        response = self.finish(note="tanpa foto")
        self.assertRedirects(
            response, reverse("courier:order_detail", args=[self.order.pk])
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.ON_DELIVERY)
        self.assertFalse(self.order.delivery_photo)
        self.assertIsNone(self.order.delivered_at)

    def test_non_image_file_is_rejected(self):
        fake = SimpleUploadedFile("x.jpg", b"bukan gambar", content_type="image/jpeg")
        self.finish(photo=fake)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.ON_DELIVERY)

    def test_unsupported_image_format_is_rejected(self):
        self.finish(photo=make_photo("x.gif", "GIF"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.ON_DELIVERY)

    def test_oversized_photo_is_rejected(self):
        from courier import forms

        original = forms.MAX_PROOF_SIZE
        forms.MAX_PROOF_SIZE = 10
        try:
            self.finish(photo=make_photo())
        finally:
            forms.MAX_PROOF_SIZE = original
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.ON_DELIVERY)

    def test_other_courier_cannot_finish_my_order(self):
        other = make_courier("kurir_lain")
        self.client.force_login(other)
        response = self.finish(photo=make_photo())
        self.assertEqual(response.status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.ON_DELIVERY)

    def test_detail_shows_upload_form_while_on_delivery(self):
        response = self.client.get(
            reverse("courier:order_detail", args=[self.order.pk])
        )
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, self.order.tracking_number)

    def test_detail_shows_photo_after_delivered(self):
        self.finish(photo=make_photo())
        self.order.refresh_from_db()
        response = self.client.get(
            reverse("courier:order_detail", args=[self.order.pk])
        )
        self.assertContains(response, self.order.delivery_photo.url)
        self.assertNotContains(response, 'enctype="multipart/form-data"')

    def test_start_delivery_records_shipped_at(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery"},
        )
        order.refresh_from_db()
        self.assertIsNotNone(order.shipped_at)


class LiveLocationTests(TestCase):
    URL = "/staff/courier/lokasi/"

    def setUp(self):
        self.courier = make_courier("kurir_gps")
        self.client.login(username="kurir_gps", password="x")

    def ping(self, lat="-1.265400", lng="116.831200", accuracy="12"):
        return self.client.post(self.URL, {"lat": lat, "lng": lng, "accuracy": accuracy})

    def test_rejected_when_not_delivering(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        r = self.ping()
        self.assertEqual(r.status_code, 409)
        from courier.models import CourierLocation

        self.assertFalse(CourierLocation.objects.exists())

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
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        order.mark_on_delivery(self.courier)
        self.assertEqual(self.ping(lat="200").status_code, 400)
        self.assertEqual(self.ping(lng="abc").status_code, 400)
        User.objects.create_user("adm_gps", password="x", role=Role.ADMIN)
        self.client.login(username="adm_gps", password="x")
        self.assertEqual(self.ping().status_code, 403)

    def test_dashboard_shows_share_panel_only_when_delivering(self):
        r = self.client.get(reverse("courier:dashboard"))
        self.assertNotContains(r, "data-live-location")
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        order.mark_on_delivery(self.courier)
        r = self.client.get(reverse("courier:dashboard"))
        self.assertContains(r, "data-live-location")


    def test_old_order_without_shipped_at_still_shows_location(self):
        order = make_order(self.courier, OrderStatus.ON_DELIVERY)  # shipped_at kosong
        self.assertIsNone(order.shipped_at)
        self.ping()
        data = self.client.get(
            reverse("customer:track_location", args=[order.tracking_number])
        ).json()
        self.assertTrue(data["live"])
