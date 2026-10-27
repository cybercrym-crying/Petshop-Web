import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from account.models import Customer, Role, User
from transaction.models import Order, OrderStatus
from store.models import Notification


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

    def test_history_filters_and_weekly_summary(self):
        done = make_order(self.courier, OrderStatus.DELIVERED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        r = self.client.get(reverse("courier:history"), {"f": "terkirim"})
        self.assertContains(r, 'class="hist-row"', count=1)
        self.assertContains(r, reverse("courier:order_detail", args=[done.pk]))
        self.assertEqual(self.client.get(reverse("courier:history"), {"f": "aneh"}).context["current"], "")
        self.assertEqual(
            [(key, n) for key, _label, n in r.context["filters"]], [("", 2), ("terkirim", 1), ("berjalan", 1)]
        )

    def test_courier_notifications_use_courier_layout(self):
        Notification.send(self.courier, "Setoran #1 diterima kasir", url="/staff/courier/setoran/")
        r = self.client.get(reverse("store:notifications"))
        self.assertContains(r, 'id="ck-side"')
        self.assertContains(r, "Setoran #1 diterima kasir")
        self.assertContains(r, "bi-wallet2")

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
        self.assertEqual(self.client.get(url).status_code, 403)  # belum verifikasi 4 digit WA
        self.client.post(reverse("customer:track_detail", args=[order.tracking_number]), {"wa4": order.phone_last4})
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


class CourierAccountTests(TestCase):
    """Kurir bisa mengubah akunnya sendiri dan mengunggah foto; foto tampil di halaman lacak."""

    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="petshop-test-media-")
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.courier = make_courier("kurir_akun")
        self.client.force_login(self.courier)

    def post_profile(self, **extra):
        data = {"form": "profile", "name": "Budi Kurir", "phone_number": "081255550000",
                "email": "", "vehicle": "Honda Beat", "plate_number": "kt 1234 ab"}
        data.update(extra)
        return self.client.post(reverse("courier:account"), data)

    def test_nav_links_to_account_and_has_collapsible_sidebar(self):
        html = self.client.get(reverse("courier:packages")).content.decode()
        self.assertIn(f'href="{reverse("courier:account")}"', html)
        self.assertIn('id="ck-side"', html)
        self.assertIn("data-ck-menu", html)
        self.assertIn("data-theme-toggle", html)

    def test_courier_updates_profile_and_photo(self):
        with override_settings(MEDIA_ROOT=self.media):
            response = self.post_profile(photo=make_photo("wajah.jpg"))
            self.assertRedirects(response, reverse("courier:account"))
            self.courier.refresh_from_db()
            profile = self.courier.courier_profile
            self.assertEqual(self.courier.name, "Budi Kurir")
            self.assertEqual(profile.vehicle, "Honda Beat")
            self.assertEqual(profile.plate_number, "KT 1234 AB")
            self.assertTrue(profile.photo.name.startswith("couriers/"))
            html = self.client.get(reverse("courier:account")).content.decode()
            self.assertIn(self.courier.photo_url, html)

            self.post_profile(remove_photo="on")
            profile.refresh_from_db()
            self.assertFalse(profile.photo)

    def test_rejects_non_image_upload(self):
        with override_settings(MEDIA_ROOT=self.media):
            fake = SimpleUploadedFile("x.jpg", b"bukan gambar", content_type="image/jpeg")
            response = self.post_profile(photo=fake)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.courier.photo_url)

    def test_courier_cannot_change_admin_fields(self):
        self.post_profile(status="OFFLINE", can_carry_pets="on", service_area="Semua")
        profile = User.objects.get(pk=self.courier.pk).courier_profile
        self.assertFalse(profile.can_carry_pets)
        self.assertEqual(profile.service_area, "")

    def test_password_change_keeps_session(self):
        response = self.client.post(reverse("courier:account"), {
            "form": "password", "old_password": "x", "new_password1": "SandiBaru#2026", "new_password2": "SandiBaru#2026"})
        self.assertRedirects(response, reverse("courier:account"))
        self.courier.refresh_from_db()
        self.assertTrue(self.courier.check_password("SandiBaru#2026"))
        self.assertEqual(self.client.get(reverse("courier:account")).status_code, 200)

    def test_photo_shows_on_customer_tracking_page(self):
        with override_settings(MEDIA_ROOT=self.media):
            self.post_profile(photo=make_photo("wajah.jpg"))
            order = make_order(self.courier, OrderStatus.ON_DELIVERY)
            self.client.logout()
            url = reverse("customer:track_detail", args=[order.tracking_number])
            self.client.post(url, {"wa4": order.phone_last4})
            html = self.client.get(url).content.decode()
        self.assertIn('class="track-courier__photo"', html)

    def test_customer_cannot_open_courier_account(self):
        self.client.force_login(Customer.objects.create(username="pel", name="Pel", phone_number="0819", address="x"))
        self.assertNotEqual(self.client.get(reverse("courier:account")).status_code, 200)


class CustomerSeesDeliveryProofTests(TestCase):
    """Foto bukti dari kurir juga terlihat oleh pelanggan di Pesanan Saya."""

    def test_delivered_order_shows_proof_photo_and_courier(self):
        media = tempfile.mkdtemp(prefix="petshop-test-media-")
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        courier = make_courier("kurir_bukti")
        with override_settings(MEDIA_ROOT=media):
            order = make_order(courier, OrderStatus.ON_DELIVERY)
            order.mark_delivered(photo=make_photo(), note="Titip di pos satpam")
            self.client.force_login(order.customer)
            html = self.client.get(reverse("customer:my_orders")).content.decode()
        self.assertIn('class="mo-proof"', html)
        self.assertIn(order.delivery_photo.url, html)
        self.assertIn("Titip di pos satpam", html)
        self.assertIn(courier.display_name, html)

    def test_proof_block_only_for_delivered_orders(self):
        order = make_order(make_courier("kurir_jalan"), OrderStatus.ON_DELIVERY)
        self.client.force_login(order.customer)
        html = self.client.get(reverse("customer:my_orders")).content.decode()
        self.assertNotIn('class="mo-proof"', html)
