from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import Customer, Role, User
from common.exceptions import PetshopError

from .models import BookingStatus, InvalidBookingTransition, Service, ServiceBooking


def tomorrow_at(hour=10):
    t = timezone.localtime() + timedelta(days=1)
    return t.replace(hour=hour, minute=0, second=0, microsecond=0)


class Fixtures:
    def make_people(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.kasir = User.objects.create_user("ksr", password="x", role=Role.CASHIER)
        self.groomer = User.objects.create_user(
            "grm", password="x", role=Role.GROOMER, first_name="Gilang"
        )
        self.groomer2 = User.objects.create_user("grm2", password="x", role=Role.GROOMER)
        self.customer = Customer.objects.create(
            name="Siti Aminah", phone_number="081300000001", address="Jl. Mawar"
        )
        self.service = Service.objects.create(name="Mandi Uji", price=50000)

    def book(self, **kw):
        data = dict(
            customer=self.customer,
            service=self.service,
            pet_name="Mochi",
            pet_type="KUCING",
            schedule=tomorrow_at(),
        )
        data.update(kw)
        return ServiceBooking.book(**data)


class CustomerTableRemovedTests(TestCase):
    def test_customer_is_a_user_with_customer_role(self):
        c = Customer.objects.create(name="Budi Santoso", phone_number="0812", address="x")
        user = User.objects.get(pk=c.pk)
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertEqual((user.first_name, user.last_name), ("Budi", "Santoso"))
        self.assertEqual(user.name, "Budi Santoso")
        self.assertEqual(user.username, "0812")
        self.assertFalse(user.has_usable_password())

    def test_customer_manager_only_sees_customers(self):
        User.objects.create_user("adm", password="x", role=Role.ADMIN)
        Customer.objects.create(name="A", phone_number="0811", address="x")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)

    def test_customer_phone_stays_unique_but_staff_may_share(self):
        from django.db import IntegrityError, transaction

        Customer.objects.create(name="A", phone_number="0811", address="x")
        User.objects.create_user("kurir", password="x", role=Role.COURIER, phone_number="0811")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("dup", password="x", role=Role.CUSTOMER, phone_number="0811")

    def test_new_roles_have_behaviors(self):
        from account.models import CashierRole, GroomerRole

        kasir = User(role=Role.CASHIER)
        groomer = User(role=Role.GROOMER)
        self.assertIsInstance(kasir.role_behavior, CashierRole)
        self.assertIsInstance(groomer.role_behavior, GroomerRole)
        self.assertEqual(kasir.dashboard_url_name, "transaction:make_transaction")
        self.assertEqual(groomer.dashboard_url_name, "service:groomer_dashboard")
        self.assertFalse(kasir.role_behavior.can_access_admin())


class BookingFlowTests(Fixtures, TestCase):
    def setUp(self):
        self.make_people()

    def test_new_booking_is_pending_with_price_snapshot(self):
        b = self.book()
        self.assertEqual(b.status, BookingStatus.PENDING)
        self.assertEqual(b.price, 50000)
        self.service.price = 99000
        self.service.save()
        b.refresh_from_db()
        self.assertEqual(b.price, 50000)

    def test_pending_to_process_to_done(self):
        b = self.book()
        b.start(self.groomer)
        self.assertEqual((b.status, b.groomer), (BookingStatus.PROCESS, self.groomer))
        self.assertIsNotNone(b.started_at)
        b.finish(self.groomer, note="Bersih")
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.DONE)
        self.assertEqual(b.groomer_note, "Bersih")

    def test_cannot_skip_or_go_back(self):
        b = self.book()
        with self.assertRaises(InvalidBookingTransition):
            b.finish(self.groomer)
        b.start(self.groomer)
        b.finish(self.groomer)
        with self.assertRaises(InvalidBookingTransition):
            b.start(self.groomer)
        self.assertTrue(issubclass(InvalidBookingTransition, PetshopError))

    def test_other_groomer_cannot_take_or_finish(self):
        b = self.book(groomer=self.groomer)
        with self.assertRaises(InvalidBookingTransition):
            b.start(self.groomer2)
        b.start(self.groomer)
        with self.assertRaises(InvalidBookingTransition):
            b.finish(self.groomer2)

    def test_service_pet_type_is_checked(self):
        dog_only = Service.objects.create(name="Anjing saja", price=1, pet_type="ANJING")
        with self.assertRaises(InvalidBookingTransition):
            self.book(service=dog_only, pet_type="KUCING")


class GroomerPageTests(Fixtures, TestCase):
    URL = "/staff/groomer/dashboard"

    def setUp(self):
        self.make_people()
        self.client.login(username="grm", password="x")

    def test_only_groomer_can_open(self):
        self.client.login(username="ksr", password="x")
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_pending_tab_shows_unassigned_and_mine_only(self):
        free = self.book(pet_name="Bebas")
        mine = self.book(pet_name="Punyaku", groomer=self.groomer)
        other = self.book(pet_name="Orang Lain", groomer=self.groomer2)
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
        shown = {b.pk for b in r.context["bookings"]}
        self.assertEqual(shown, {free.pk, mine.pk})
        self.assertNotIn(other.pk, shown)

    def test_take_and_finish_through_page(self):
        b = self.book()
        url = reverse("service:groomer_update_status", args=[b.pk])
        r = self.client.post(url, {"action": "start"})
        self.assertRedirects(r, f"{self.URL}?status=proses", fetch_redirect_response=False)
        b.refresh_from_db()
        self.assertEqual((b.status, b.groomer), (BookingStatus.PROCESS, self.groomer))
        self.client.post(url, {"action": "finish", "note": "Wangi"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.DONE)
        r = self.client.get(self.URL, {"status": "selesai"})
        self.assertContains(r, "Mochi")

    def test_cannot_open_booking_of_other_groomer(self):
        b = self.book(groomer=self.groomer2)
        r = self.client.get(reverse("service:groomer_booking_detail", args=[b.pk]))
        self.assertEqual(r.status_code, 404)


class StaffAndCustomerPagesTests(Fixtures, TestCase):
    def setUp(self):
        self.make_people()

    def test_kasir_can_use_pos_and_bookings_but_not_admin_pages(self):
        self.client.login(username="ksr", password="x")
        self.assertEqual(self.client.get("/staff/admin/make_transaction/").status_code, 200)
        self.assertEqual(self.client.get("/staff/layanan/booking/").status_code, 200)
        self.assertEqual(self.client.get("/staff/admin/manage_account").status_code, 403)
        self.assertEqual(self.client.get("/staff/admin/layanan/").status_code, 403)

    def test_kasir_creates_walk_in_booking(self):
        self.client.login(username="ksr", password="x")
        self.client.post(
            reverse("service:create_booking"),
            {
                "customer": self.customer.pk,
                "service": self.service.pk,
                "pet_name": "Kopi",
                "pet_type": "ANJING",
                "schedule": tomorrow_at(11).strftime("%Y-%m-%dT%H:%M"),
                "groomer": self.groomer.pk,
            },
        )
        b = ServiceBooking.objects.get()
        self.assertEqual((b.pet_name, b.groomer, b.created_by), ("Kopi", self.groomer, self.kasir))

    def test_customer_books_online_and_sees_status(self):
        self.customer.set_password("rahasia-123")
        self.customer.save()
        self.client.login(username=self.customer.username, password="rahasia-123")
        r = self.client.post(
            reverse("service:catalog"),
            {
                "service": self.service.pk,
                "pet_name": "Luna",
                "pet_type": "KUCING",
                "schedule": tomorrow_at(9).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertRedirects(r, reverse("service:my_bookings"), fetch_redirect_response=False)
        r = self.client.get(reverse("service:my_bookings"))
        self.assertContains(r, "Luna")
        self.assertContains(r, "Pending")

    def test_booking_outside_opening_hours_rejected(self):
        self.customer.set_password("rahasia-123")
        self.customer.save()
        self.client.login(username=self.customer.username, password="rahasia-123")
        self.client.post(
            reverse("service:catalog"),
            {
                "service": self.service.pk,
                "pet_name": "Luna",
                "pet_type": "KUCING",
                "schedule": tomorrow_at(23).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertFalse(ServiceBooking.objects.exists())

    def test_anonymous_booking_redirects_to_login(self):
        r = self.client.post(reverse("service:catalog"), {})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r["Location"])
        self.assertEqual(self.client.get(reverse("service:catalog")).status_code, 200)

    def test_register_creates_customer_and_logs_in(self):
        r = self.client.post(
            reverse("register"),
            {
                "name": "Dewi Kartika",
                "username": "dewi",
                "phone_number": "+62 813 1111 2222",
                "address": "Jl. Melati 7",
                "password1": "kucingku-123",
                "password2": "kucingku-123",
            },
        )
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(username="dewi")
        self.assertEqual((user.role, user.phone_number), (Role.CUSTOMER, "081311112222"))
        self.assertEqual(self.client.get(reverse("service:my_bookings")).status_code, 200)

    def test_groomer_profile_shows_booking_stats(self):
        b = self.book()
        b.start(self.groomer)
        self.client.login(username="adm", password="x")
        r = self.client.get(f"/staff/admin/employee/{self.groomer.pk}/")
        self.assertEqual(r.status_code, 200)
        by = {s["label"]: s["value"] for s in r.context["stats"]}
        self.assertEqual(by, {"Ditangani": 1, "Sedang diproses": 1, "Selesai": 0})
