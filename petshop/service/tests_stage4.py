"""Tes tahap 4: alur servis bertahap (konfirmasi, check-in & antrean, tahapan + foto),
antar-jemput hewan, profil hewan & pengingat, ulasan, dan komplain."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import Customer, Role, User
from common.tests_helpers import tiny_photo
from courier.models import CourierLocation, CourierProfile
from store.models import ActivityLog, Complaint, ComplaintStatus, Notification, StoreSettings
from transaction.models import Order, OrderStatus

from .models import BookingStatus, InvalidBookingTransition, Pet, Service, ServiceBooking, ServiceStep
from .tests import Fixtures, tomorrow_at

HOME = (Decimal("-1.255400"), Decimal("116.831200"))  # ±1,1 km dari toko


class Stage4Fixtures(Fixtures):
    def make_people(self):
        super().make_people()
        self.customer.set_password("rahasia-123")
        self.customer.save()
        self.kurir = User.objects.create_user("krr", password="x", role=Role.COURIER)
        CourierProfile.objects.create(user=self.kurir, can_carry_pets=True)
        self.kurir_paket = User.objects.create_user("krr2", password="x", role=Role.COURIER)
        CourierProfile.objects.create(user=self.kurir_paket, can_carry_pets=False)

    def login_customer(self):
        self.client.login(username=self.customer.username, password="rahasia-123")

    def gps(self, courier=None):
        CourierLocation.objects.create(
            courier=courier or self.kurir, latitude=Decimal("-1.260000"), longitude=Decimal("116.831200"),
            recorded_at=timezone.now(),
        )


class ConfirmAndQueueTests(Stage4Fixtures, TestCase):
    def setUp(self):
        self.make_people()

    def test_cashier_confirms_and_customer_is_notified(self):
        b = self.book()
        self.client.force_login(self.kasir)
        self.client.post(reverse("service:booking_action", args=[b.pk]), {"action": "confirm"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.SCHEDULED)
        self.assertEqual(b.confirmed_by, self.kasir)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="terjadwal").exists())

    def test_staff_walk_in_is_scheduled_immediately(self):
        self.client.force_login(self.kasir)
        self.client.post(reverse("service:create_booking"), {
            "customer": self.customer.pk, "service": self.service.pk, "pet_name": "Kopi",
            "pet_type": "ANJING", "schedule": tomorrow_at(11).strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(ServiceBooking.objects.get().status, BookingStatus.SCHEDULED)

    def test_check_in_by_qr_gives_daily_queue_numbers_and_eta(self):
        first, second = self.book(), self.book(pet_name="Kopi")
        self.client.force_login(self.kasir)
        r = self.client.get(reverse("service:check_in"), {"kode": first.checkin_payload})
        self.assertEqual(r.context["booking"], first)
        for b in (first, second):
            self.client.post(reverse("service:check_in"), {
                "action": "checkin", "booking": b.pk, "weight_kg": "4.2", "condition": "Sehat",
                "photo": tiny_photo(),
            })
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.queue_label, second.queue_label), ("G-001", "G-002"))
        self.assertEqual(first.checkin_weight_kg, Decimal("4.20"))
        self.assertTrue(first.checkin_photo)
        self.assertEqual((first.queue_position(), second.queue_position()), (0, 1))
        # Dua groomer: booking kedua menunggu 60 menit layanan pertama / 2.
        self.assertEqual(second.queue_eta_minutes(), 30)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="G-002").exists())

    def test_bare_booking_number_is_not_enough_to_check_in(self):
        b = self.book()
        self.assertIsNone(ServiceBooking.find_by_code(str(b.pk)))
        self.assertIsNone(ServiceBooking.find_by_code(f"PSB:{b.pk}:SALAH123"))
        self.assertEqual(ServiceBooking.find_by_code(b.checkin_code.lower()), b)

    def test_late_booking_can_be_marked_no_show(self):
        b = self.book(schedule=timezone.now() - timedelta(hours=1))
        self.client.force_login(self.kasir)
        self.client.post(reverse("service:booking_action", args=[b.pk]), {"action": "no_show"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.NO_SHOW)
        future = self.book()
        with self.assertRaises(InvalidBookingTransition):
            future.mark_no_show()

    def test_check_in_page_shows_queue_board(self):
        b = self.book()
        b.check_in(self.kasir)
        self.client.force_login(self.kasir)
        r = self.client.get(reverse("service:check_in"))
        self.assertContains(r, "G-001")
        self.assertContains(r, "data-qr-scanner")
        self.client.force_login(self.groomer)
        self.assertEqual(self.client.get(reverse("service:check_in")).status_code, 403)


class StepTemplateTests(Stage4Fixtures, TestCase):
    def setUp(self):
        self.make_people()
        ServiceStep.objects.create(service=self.service, position=1, name="Mandi", needs_photo=True)
        ServiceStep.objects.create(service=self.service, position=2, name="Pengeringan", needs_photo=False)

    def test_steps_follow_template_and_photo_rule(self):
        b = self.book()
        b.check_in(self.kasir)
        b.start(self.groomer)
        self.assertEqual([s.name for s in b.steps.all()], ["Mandi", "Pengeringan"])
        with self.assertRaises(InvalidBookingTransition):
            b.complete_step(self.groomer, None)  # Mandi wajib foto
        b.complete_step(self.groomer, tiny_photo())
        b.complete_step(self.groomer, None, note="Kering & wangi")  # foto opsional
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.READY)
        self.assertEqual(b.groomer_note, "Kering & wangi")

    def test_ready_notifies_customer_and_cashier(self):
        b = self.book()
        b.check_in(self.kasir)
        self.client.force_login(self.groomer)
        url = reverse("service:groomer_update_status", args=[b.pk])
        self.client.post(url, {"action": "start"})
        self.client.post(url, {"action": "step", "photo": tiny_photo()})
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="Mandi selesai").exists())
        self.client.post(url, {"action": "step"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.READY)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="siap diambil").exists())
        self.assertTrue(Notification.objects.filter(user=self.kasir, title__contains="siap").exists())
        self.login_customer()
        r = self.client.get(reverse("service:my_bookings"))
        self.assertContains(r, "Foto tahap Mandi")

    def test_admin_edits_steps_and_cashier_cannot(self):
        url = reverse("service:service_steps", args=[self.service.pk])
        self.client.force_login(self.kasir)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        steps = list(self.service.steps.all())
        data = {
            "steps-TOTAL_FORMS": "3", "steps-INITIAL_FORMS": "2", "steps-MIN_NUM_FORMS": "0", "steps-MAX_NUM_FORMS": "1000",
            "steps-0-id": steps[0].pk, "steps-0-position": "2", "steps-0-name": "Mandi", "steps-0-needs_photo": "on",
            "steps-1-id": steps[1].pk, "steps-1-position": "3", "steps-1-name": "Pengeringan", "steps-1-DELETE": "on",
            "steps-2-position": "1", "steps-2-name": "Potong kuku", "steps-2-needs_photo": "on",
        }
        r = self.client.post(url, data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.service.step_names(), ["Potong kuku", "Mandi"])
        self.assertEqual(list(self.service.steps.values_list("position", flat=True)), [1, 2])


    def test_new_service_goes_to_steps_and_list_shows_steps(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("service:add_service"), {
            "name": "Layanan Baru", "pet_type": "SEMUA", "price": "40000", "duration_minutes": "45",
            "description": "", "is_active": "on",
        })
        service = Service.objects.get(name="Layanan Baru")
        self.assertRedirects(r, reverse("service:service_steps", args=[service.pk]))
        r = self.client.post(reverse("service:edit_service", args=[service.pk]), {
            "name": "Layanan Baru", "pet_type": "SEMUA", "price": "45000", "duration_minutes": "45",
        })
        self.assertRedirects(r, reverse("service:manage_services"))
        service.refresh_from_db()
        self.assertFalse(service.is_active)
        r = self.client.get(reverse("service:manage_services"))
        self.assertContains(r, "Memakai tahapan bawaan")
        self.assertContains(r, "Mandi")


class PetTransportTests(Stage4Fixtures, TestCase):
    def setUp(self):
        self.make_people()

    def transport_booking(self, **kw):
        b = self.book(pickup=True, return_trip=True, location=HOME, address="Jl. Mawar 1", confirmed=True, **kw)
        b.assign_pet_courier(self.kurir)
        return b

    def test_fee_is_per_trip_and_range_is_checked(self):
        store = StoreSettings.current()
        both = self.book(pickup=True, return_trip=True, location=HOME)
        one = self.book(pickup=True, location=HOME)
        self.assertEqual(both.transport_fee, store.pickup_base_fee * 2)
        self.assertEqual(one.transport_fee, store.pickup_base_fee)
        self.assertEqual(both.total_price, 50000 + store.pickup_base_fee * 2)
        with self.assertRaises(InvalidBookingTransition):
            self.book(pickup=True, location=(Decimal("-0.500000"), Decimal("117.150000")))  # ±90 km
        with self.assertRaises(InvalidBookingTransition):
            self.book(pickup=True)  # tanpa pin

    def test_only_pet_couriers_can_be_assigned(self):
        b = self.book(pickup=True, location=HOME)
        with self.assertRaises(InvalidBookingTransition):
            b.assign_pet_courier(self.kurir_paket)
        plain = self.book()
        with self.assertRaises(InvalidBookingTransition):
            plain.assign_pet_courier(self.kurir)

    def test_full_pickup_and_return_flow_with_live_map(self):
        b = self.transport_booking()
        self.client.force_login(self.kurir)
        trip = reverse("service:courier_pet_trip", args=[b.pk])
        r = self.client.post(trip, {"action": "start_pickup"}, follow=True)
        self.assertContains(r, "GPS")  # GPS mati: ditolak
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.SCHEDULED)
        self.gps()
        self.client.post(trip, {"action": "start_pickup"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.PICKUP)
        # Pemilik melihat kurir menuju rumahnya.
        self.login_customer()
        data = self.client.get(reverse("service:booking_location", args=[b.pk])).json()
        self.assertTrue(data["live"])
        self.assertEqual(data["destination_label"], "alamat Anda")
        self.assertIn("eta_minutes", data)
        # Kurir: QR salah ditolak, QR benar + foto -> hewan dibawa.
        self.client.force_login(self.kurir)
        check = self.client.post(reverse("service:courier_pet_check", args=[b.pk]), {"code": "SALAH123"})
        self.assertEqual(check.status_code, 400)
        self.client.post(trip, {"action": "collect", "code": b.checkin_payload, "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertIsNotNone(b.pet_collected_at)
        self.assertTrue(b.pickup_photo)
        self.login_customer()
        data = self.client.get(reverse("service:booking_location", args=[b.pk])).json()
        self.assertEqual(data["destination_label"], "toko")
        # Toko: check-in, groomer kerjakan semua tahap.
        b.check_in(self.kasir)
        b.start(self.groomer)
        self.finish_all(b, self.groomer)
        # Antar pulang baru bisa setelah lunas.
        self.client.force_login(self.kurir)
        self.assertContains(self.client.get(trip), "Menunggu pembayaran pelanggan")
        self.client.post(trip, {"action": "start_return", "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.READY)
        from common.tests_helpers import pay_booking_at_counter

        pay_booking_at_counter(b, self.kasir)
        self.client.post(trip, {"action": "start_return", "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.RETURNING)
        self.client.post(trip, {"action": "deliver", "code": "SALAH123", "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.RETURNING)
        self.client.post(trip, {"action": "deliver", "code": b.checkin_code, "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.DONE)
        self.assertTrue(b.return_photo)
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains="sampai di rumah").exists())

    def test_kasir_books_pickup_with_cod_and_courier_collects_cash(self):
        """Booking manual lewat telepon: jemput + antar pulang, bayar tunai ke kurir (COD), lalu disetor."""
        from courier.models import CashRemittance

        self.client.force_login(self.kasir)
        data = {
            "customer": self.customer.pk, "service": self.service.pk, "pet_name": "Kopi", "pet_type": "KUCING",
            "schedule": tomorrow_at(10).strftime("%Y-%m-%dT%H:%M"), "pickup": "on", "return_trip": "on",
            "latitude": str(HOME[0]), "longitude": str(HOME[1]), "address": "Jl. Mawar 1", "payment_choice": "COD",
        }
        # COD tanpa antar pulang ditolak.
        self.client.post(reverse("service:create_booking"), {**data, "return_trip": ""})
        self.assertFalse(ServiceBooking.objects.exists())
        r = self.client.post(reverse("service:create_booking"), data)
        b = ServiceBooking.objects.get()
        self.assertRedirects(r, reverse("service:manage_bookings") + f"?day={tomorrow_at(10).date()}&id={b.pk}",
                             fetch_redirect_response=False)
        self.assertEqual((b.status, b.payment_choice, b.pickup_requested, b.return_requested),
                         (BookingStatus.SCHEDULED, "COD", True, True))
        self.assertGreater(b.transport_fee, 0)
        b.assign_pet_courier(self.kurir)
        # Panel kasir: tautan QR berkunci + pesan WhatsApp siap kirim.
        panel = self.client.get(reverse("service:manage_bookings") + f"?day={tomorrow_at(10).date()}&id={b.pk}")
        link = panel.context["share_link"]
        self.assertIn("?k=", link)
        self.assertIn("wa.me/", panel.context["share_wa_url"])
        path = link.split("testserver", 1)[1]
        self.client.logout()
        public = self.client.get(path)
        self.assertContains(public, b.checkin_code)
        self.assertContains(public, "COD")
        self.assertEqual(self.client.get(path.split("?")[0] + "?k=salah").status_code, 404)
        self.assertEqual(self.client.get(reverse("service:booking_share_qr", args=[b.pk]) + "?k=salah").status_code, 404)
        # Jemput, kerjakan, lalu antar pulang tanpa menunggu lunas.
        self.gps()
        self.client.force_login(self.kurir)
        trip = reverse("service:courier_pet_trip", args=[b.pk])
        self.client.post(trip, {"action": "start_pickup"})
        self.client.post(trip, {"action": "collect", "code": b.checkin_payload, "photo": tiny_photo()})
        b.refresh_from_db()
        b.check_in(self.kasir)
        b.start(self.groomer)
        self.finish_all(b, self.groomer)
        self.assertEqual(self.client.get(trip).context["step"], "start_return")
        self.client.post(trip, {"action": "start_return", "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.RETURNING)
        self.assertContains(self.client.get(trip), 'name="cash_received"')
        # Tanpa centang uang diterima: belum selesai.
        self.client.post(trip, {"action": "deliver", "code": b.checkin_code, "photo": tiny_photo()})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.RETURNING)
        self.client.post(trip, {"action": "deliver", "code": b.checkin_code, "photo": tiny_photo(), "cash_received": "1"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.DONE)
        self.assertTrue(b.is_paid)
        self.assertEqual(b.cash_collected, b.total_price)
        receipt = b.payment_line.order
        self.assertEqual((receipt.total_payment, receipt.payment_method), (b.total_price, "TUNAI"))
        self.assertFalse(receipt.payments.exists())  # uang masuk laci lewat setoran, bukan kas kasir
        # Uang muncul di Setoran COD kurir lalu disetor ke kasir.
        cash = self.client.get(reverse("courier:cash"))
        self.assertEqual(cash.context["on_hand_total"], b.total_price)
        self.client.post(reverse("courier:cash"))
        remittance = CashRemittance.objects.get()
        self.assertEqual((remittance.amount, remittance.item_count), (b.total_price, 1))
        b.refresh_from_db()
        self.assertEqual(b.remittance, remittance)
        self.client.force_login(self.kasir)
        page = self.client.get(reverse("transaction:remittances"))
        self.assertContains(page, f"Booking #{b.pk}")

    def test_pickup_records_condition_and_arrival_photo_for_cashier(self):
        b = self.transport_booking()
        self.client.force_login(self.kurir)
        self.gps()
        trip = reverse("service:courier_pet_trip", args=[b.pk])
        # Foto tiba belum bisa sebelum hewan dijemput.
        self.client.post(trip, {"action": "start_pickup"})
        self.client.post(trip, {"action": "arrive", "photo": tiny_photo()})
        self.assertFalse(ActivityLog.objects.filter(action="Tiba di toko").exists())
        self.client.post(trip, {"action": "collect", "code": b.checkin_payload, "photo": tiny_photo(),
                                "condition": ["Sehat", "Gelisah", "Palsu"], "note": "takut motor"})
        log = ActivityLog.objects.get(action="Hewan dijemput kurir")
        self.assertEqual(log.detail, "Kondisi: Sehat, Gelisah. takut motor")
        page = self.client.get(trip)
        self.assertEqual(page.context["step"], "arrive")
        self.assertContains(page, 'value="arrive"')
        self.assertContains(page, "Bukti perjalanan")
        # Foto tiba wajib, lalu tersimpan sekali saja.
        self.client.post(trip, {"action": "arrive"})
        self.assertFalse(ActivityLog.objects.filter(action="Tiba di toko").exists())
        self.client.post(trip, {"action": "arrive", "photo": tiny_photo(), "latitude": "-1.260000", "longitude": "116.831200"})
        arrived = ActivityLog.objects.get(action="Tiba di toko")
        self.assertTrue(arrived.photo)
        self.assertIsNotNone(arrived.latitude)
        self.client.post(trip, {"action": "arrive", "photo": tiny_photo()})
        self.assertEqual(ActivityLog.objects.filter(action="Tiba di toko").count(), 1)
        self.assertEqual(self.client.get(trip).context["step"], "at_store")
        # Kasir melihat foto bukti kurir di halaman check-in booking ini.
        self.client.force_login(self.kasir)
        r = self.client.get(reverse("service:check_in"), {"booking": b.pk})
        self.assertContains(r, "Bukti foto dari kurir")
        self.assertContains(r, arrived.photo.url)

    def test_other_courier_and_other_customer_are_blocked(self):
        b = self.transport_booking()
        self.client.force_login(self.kurir_paket)
        self.assertEqual(self.client.get(reverse("service:courier_pet_trip", args=[b.pk])).status_code, 404)
        other = Customer.objects.create(name="Lain", phone_number="0819", address="x")
        other.set_password("rahasia-123")
        other.save()
        self.client.login(username=other.username, password="rahasia-123")
        self.assertEqual(self.client.get(reverse("service:booking_location", args=[b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("service:booking_qr", args=[b.pk])).status_code, 404)

    def test_pet_tab_only_for_pet_couriers(self):
        self.client.force_login(self.kurir)
        self.assertContains(self.client.get(reverse("courier:dashboard")), reverse("service:courier_pets"))
        self.client.force_login(self.kurir_paket)
        self.assertNotContains(self.client.get(reverse("courier:dashboard")), reverse("service:courier_pets"))


class PetProfileTests(Stage4Fixtures, TestCase):
    def setUp(self):
        self.make_people()
        self.login_customer()

    def test_add_pet_and_book_with_it(self):
        self.client.post(reverse("service:add_pet"), {
            "name": "Mochi", "pet_type": "KUCING", "breed": "Persia", "sex": "BETINA",
            "birth_date": "2023-01-15", "weight_kg": "3.5", "notes": "Takut pengering",
        })
        pet = Pet.objects.get(owner=self.customer)
        r = self.client.post(reverse("service:catalog"), {
            "service": self.service.pk, "pet": pet.pk,
            "schedule": tomorrow_at(10).strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(r.status_code, 302)
        b = ServiceBooking.objects.get()
        self.assertEqual((b.pet, b.pet_name, b.pet_type), (pet, "Mochi", "KUCING"))
        self.assertTrue(Notification.objects.filter(user=self.kasir, title__contains="menunggu konfirmasi").exists())

    def test_cannot_use_or_edit_someone_elses_pet(self):
        other = Customer.objects.create(name="Lain", phone_number="0819", address="x")
        theirs = Pet.objects.create(owner=other, name="Bukan", pet_type="KUCING")
        self.client.post(reverse("service:catalog"), {
            "service": self.service.pk, "pet": theirs.pk,
            "schedule": tomorrow_at(10).strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertFalse(ServiceBooking.objects.exists())
        self.assertEqual(self.client.get(reverse("service:edit_pet", args=[theirs.pk])).status_code, 404)

    def test_booking_with_pickup_needs_pin_on_map(self):
        base = {"service": self.service.pk, "pet_name": "Luna", "pet_type": "KUCING",
                "schedule": tomorrow_at(10).strftime("%Y-%m-%dT%H:%M"), "pickup": "on"}
        self.client.post(reverse("service:catalog"), base)
        self.assertFalse(ServiceBooking.objects.exists())
        self.client.post(reverse("service:catalog"), {**base, "latitude": "-1.255400", "longitude": "116.831200"})
        b = ServiceBooking.objects.get()
        self.assertTrue(b.pickup_requested)
        self.assertFalse(b.return_requested)
        self.assertGreater(b.transport_fee, 0)

    def test_grooming_reminder_is_sent_once_per_last_service(self):
        pet = Pet.objects.create(owner=self.customer, name="Mochi", pet_type="KUCING")
        b = self.book(pet=pet)
        b.check_in(self.kasir)
        b.start(self.groomer)
        self.finish_all(b, self.groomer)
        ServiceBooking.objects.filter(pk=b.pk).update(finished_at=timezone.now() - timedelta(days=31))
        call_command("send_grooming_reminders", stdout=StringIO())
        call_command("send_grooming_reminders", stdout=StringIO())
        self.assertEqual(Notification.objects.filter(user=self.customer, title__contains="grooming lagi").count(), 1)
        r = self.client.get(reverse("customer:dashboard"))
        self.assertContains(r, "Waktunya grooming lagi")


class RatingAndComplaintTests(Stage4Fixtures, TestCase):
    def setUp(self):
        self.make_people()
        self.login_customer()

    def test_rate_finished_booking_once(self):
        b = self.book()
        url = reverse("service:rate_booking", args=[b.pk])
        self.client.post(url, {"stars": "5"})
        b.refresh_from_db()
        self.assertIsNone(b.rating)  # belum selesai
        b.check_in(self.kasir)
        b.start(self.groomer)
        self.finish_all(b, self.groomer)
        from common.tests_helpers import pay_booking_at_counter

        pay_booking_at_counter(b, self.kasir)
        b.hand_to_owner()
        self.client.post(url, {"stars": "4", "review": "Rapi"})
        self.client.post(url, {"stars": "1"})
        b.refresh_from_db()
        self.assertEqual((b.rating, b.review), (4, "Rapi"))
        self.client.force_login(self.kasir)
        self.assertContains(self.client.get(reverse("store:reviews")), "Rapi")

    def test_rate_delivered_order(self):
        from transaction.tests import make_product

        product = make_product("Whiskas", stock=5, price=10000)
        order = Order.place_online(self.customer, [(product.pk, 1)], "TUNAI")
        url = reverse("customer:rate_order", args=[order.pk])
        self.client.post(url, {"stars": "5"})
        order.refresh_from_db()
        self.assertIsNone(order.rating)
        Order.objects.filter(pk=order.pk).update(order_status=OrderStatus.DELIVERED)
        self.client.post(url, {"stars": "5", "review": "Cepat"})
        order.refresh_from_db()
        self.assertEqual(order.rating, 5)

    def test_complaint_with_photo_and_staff_reply(self):
        b = self.book()
        r = self.client.post(reverse("store:complaints"), {
            "category": "LAYANAN", "booking": b.pk, "message": "Kuku terlalu pendek", "photo": tiny_photo(),
        })
        self.assertEqual(r.status_code, 302)
        c = Complaint.objects.get()
        self.assertTrue(c.photo)
        self.assertTrue(Notification.objects.filter(user=self.kasir, title__contains="Komplain baru").exists())
        self.client.force_login(self.kasir)
        url = reverse("store:staff_complaint", args=[c.pk])
        self.client.post(url, {"status": "SELESAI", "response": ""})
        c.refresh_from_db()
        self.assertEqual(c.status, ComplaintStatus.OPEN)  # selesai wajib ada balasan
        self.client.post(url, {"status": "SELESAI", "response": "Maaf, kami beri potongan berikutnya."})
        c.refresh_from_db()
        self.assertEqual((c.status, c.handled_by), (ComplaintStatus.RESOLVED, self.kasir))
        self.assertTrue(Notification.objects.filter(user=self.customer, title__contains=f"Komplain #{c.pk}").exists())

    def test_complaint_cannot_point_to_someone_elses_order(self):
        from transaction.tests import make_product

        other = Customer.objects.create(name="Lain", phone_number="0819", address="x")
        product = make_product("Whiskas", stock=5, price=10000)
        theirs = Order.place_online(other, [(product.pk, 1)], "TUNAI")
        self.client.post(reverse("store:complaints"), {"category": "PRODUK", "order": theirs.pk, "message": "x"})
        self.assertFalse(Complaint.objects.exists())

    def test_staff_pages_render(self):
        self.client.force_login(self.kasir)
        for name in ("store:staff_complaints", "store:reviews", "service:manage_bookings", "service:check_in"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.client.force_login(self.groomer)
        self.assertEqual(self.client.get(reverse("store:staff_complaints")).status_code, 403)


class OneTaskPerCourierTests(Stage4Fixtures, TestCase):
    """Kurir yang sedang antar-jemput hewan tidak membawa paket, dan sebaliknya."""

    def setUp(self):
        from transaction.tests import make_product

        self.make_people()
        self.product = make_product("Pakan Uji", stock=10)
        self.trip = self.book(pickup=True, return_trip=True, location=HOME, address="Jl. Mawar 1", confirmed=True)
        self.trip.assign_pet_courier(self.kurir)

    def ready_order(self):
        order = Order.place_online(self.customer, [(self.product.pk, 1)], "TUNAI", address="Jl. Mawar 1", location=HOME)
        order.confirm(self.kasir)
        order.refresh_from_db()
        return order

    def test_courier_on_pet_trip_cannot_take_packages(self):
        from transaction.models import InvalidTransition

        self.trip.start_pickup(self.kurir)
        order = self.ready_order()
        with self.assertRaises(InvalidTransition):
            order.pickup_by(self.kurir)
        with self.assertRaises(InvalidTransition):
            order.assign_courier(self.kurir)
        # Kurir lain tetap bisa.
        order.pickup_by(self.kurir_paket)
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, OrderStatus.ON_DELIVERY)

    def test_courier_pages_hide_package_scan_during_pet_trip(self):
        self.trip.start_pickup(self.kurir)
        self.client.force_login(self.kurir)
        r = self.client.get(reverse("courier:pickup"))
        self.assertContains(r, reverse("service:courier_pet_trip", args=[self.trip.pk]))
        self.assertNotContains(r, 'id="pickup-code"')
        self.assertContains(self.client.get(reverse("courier:dashboard")), "Buka tugas hewan")

    def test_packages_are_allowed_again_after_the_trip(self):
        self.trip.start_pickup(self.kurir)
        self.trip.collect_pet(self.kurir, self.trip.checkin_code, tiny_photo())
        self.trip.check_in(self.kasir)  # hewan sudah di toko: tugas jemput selesai
        self.ready_order().pickup_by(self.kurir)

    def test_courier_carrying_packages_cannot_start_a_pet_trip(self):
        self.ready_order().pickup_by(self.kurir)
        with self.assertRaises(InvalidBookingTransition):
            self.trip.start_pickup(self.kurir)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, BookingStatus.SCHEDULED)

    def test_staff_dropdown_marks_busy_courier(self):
        self.trip.start_pickup(self.kurir)
        self.ready_order()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("transaction:manage_transaction")), "(sedang antar-jemput hewan)")

    def test_route_shows_next_pet_task_locked_while_carrying_packages(self):
        self.ready_order().pickup_by(self.kurir)
        self.client.force_login(self.kurir)
        r = self.client.get(reverse("courier:dashboard"))
        self.assertEqual(r.context["pet_task"], self.trip)
        self.assertEqual(r.context["ck_pet_count"], 1)
        self.assertContains(r, reverse("service:courier_pet_trip", args=[self.trip.pk]))
        self.assertContains(r, "Antar 1 paket dulu sebelum berangkat.")

    def test_trip_page_lists_pickup_steps_in_order(self):
        self.trip.start_pickup(self.kurir)
        self.client.force_login(self.kurir)
        r = self.client.get(reverse("service:courier_pet_trip", args=[self.trip.pk]))
        self.assertEqual([state for _label, state, _at in r.context["trip_steps"]], ["done", "now", "todo"])
        self.assertContains(r, 'aria-current="step"')


class BookingListLayoutTests(Stage4Fixtures, TestCase):
    """Halaman booking kasir: pilih tanggal, kelompok, dan panel detail."""

    def setUp(self):
        self.make_people()
        self.client.force_login(self.kasir)

    def test_day_group_and_panel(self):
        besok = tomorrow_at(9)
        pending = self.book(schedule=besok)
        sore = self.book(schedule=besok.replace(hour=16), pet_name="Kopi")
        sore.confirm(self.kasir)
        sore.groomer = self.groomer
        sore.save(update_fields=["groomer"])
        url = reverse("service:manage_bookings")
        day = besok.date().isoformat()

        res = self.client.get(url, {"day": day})
        self.assertEqual(res.status_code, 200)
        self.assertEqual({b.pk for b in res.context["bookings"]}, {pending.pk, sore.pk})
        # Tanpa id, panel memilih booking yang perlu tindakan (menunggu konfirmasi).
        self.assertEqual(res.context["selected"].pk, pending.pk)
        self.assertContains(res, "Konfirmasi booking")

        res = self.client.get(url, {"day": day, "g": "aksi"})
        self.assertEqual([b.pk for b in res.context["bookings"]], [pending.pk])

        res = self.client.get(url, {"day": day, "id": sore.pk})
        self.assertEqual(res.context["selected"].pk, sore.pk)
        self.assertContains(res, "has-pick")

        # Tanggal lain tidak menampilkan booking besok, tapi pencarian mencari semua tanggal.
        res = self.client.get(url)
        self.assertNotIn(sore.pk, {b.pk for b in res.context["bookings"]})
        res = self.client.get(url, {"q": "Kopi"})
        self.assertEqual([b.pk for b in res.context["bookings"]], [sore.pk])


class PaymentDeadlineTests(Stage4Fixtures, TestCase):
    """Transfer/QRIS yang belum dibayar 1 jam setelah dikonfirmasi dibatalkan otomatis."""

    def setUp(self):
        self.make_people()

    def test_default_deadline_is_one_hour(self):
        self.assertEqual(StoreSettings.current().payment_deadline_hours, 1)

    def test_transfer_booking_expires_one_hour_after_confirmation(self):
        b = self.book(payment_choice="TRANSFER")
        self.assertIsNone(b.payment_due_at)
        b.confirm(self.kasir)
        self.assertAlmostEqual(b.payment_due_at, timezone.now() + timedelta(hours=1), delta=timedelta(seconds=30))
        self.assertEqual(ServiceBooking.cancel_expired(), 0)

        ServiceBooking.objects.filter(pk=b.pk).update(payment_due_at=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.kasir)
        self.client.get(reverse("service:manage_bookings"))
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.CANCELLED)
        self.assertTrue(Notification.objects.filter(user=self.customer, title=f"Booking #{b.pk} dibatalkan").exists())

    def test_pay_later_and_sent_proof_are_not_cancelled(self):
        later = self.book()
        later.confirm(self.kasir)
        self.assertIsNone(later.payment_due_at)
        sent = self.book(payment_choice="TRANSFER", pet_name="Kopi", schedule=tomorrow_at(13))
        sent.confirm(self.kasir)
        sent.submit_payment_proof(self.customer, tiny_photo())
        ServiceBooking.objects.filter(pk=sent.pk).update(payment_due_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(ServiceBooking.cancel_expired(), 0)
        # Bukti ditolak: pelanggan diberi waktu lagi, bukan langsung batal.
        sent.refresh_from_db()
        sent.reject_transfer(self.kasir, "Nominal kurang")
        self.assertGreater(sent.payment_due_at, timezone.now())
        self.assertEqual(ServiceBooking.cancel_expired(), 0)

    def test_customer_chooses_transfer_when_booking(self):
        self.login_customer()
        self.client.post(reverse("service:catalog"), {
            "service": self.service.pk, "pet_name": "Mochi", "pet_type": "KUCING",
            "schedule": tomorrow_at(10).strftime("%Y-%m-%dT%H:%M"), "payment_choice": "TRANSFER",
        })
        self.assertEqual(ServiceBooking.objects.get().payment_choice, "TRANSFER")
