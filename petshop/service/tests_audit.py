"""Tes pembatalan booking, kapasitas jadwal online, dan batas jam tutup."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse

from account.models import Customer
from store.models import Notification

from .forms import BookingForm
from .models import BookingStatus, InvalidBookingTransition, Service, ServiceBooking
from .tests import Fixtures, tomorrow_at


class BookingCancelTests(Fixtures, TestCase):
    def setUp(self):
        self.make_people()
        self.customer.set_password("rahasia-123")
        self.customer.save()

    def test_customer_cancels_own_pending_booking(self):
        booking = self.book()
        self.client.login(username=self.customer.username, password="rahasia-123")
        url = reverse("service:cancel_my_booking", args=[booking.pk])
        # Tanpa alasan ditolak; pilihan "lain" wajib disertai keterangan.
        self.client.post(url)
        self.client.post(url, {"reason_choice": "lain", "reason_note": ""})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.client.post(url, {"reason_choice": "Hewan sedang sakit", "reason_note": "flu"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual((booking.cancel_reason, booking.cancelled_by), ("Hewan sedang sakit: flu", self.customer))
        self.assertEqual(booking.cancelled_by_label, "Pelanggan")
        page = self.client.get(reverse("service:my_bookings"))
        self.assertContains(page, "Hewan sedang sakit: flu")
        # Staf diberi tahu beserta alasannya.
        self.assertTrue(Notification.objects.filter(user=self.kasir, body="Hewan sedang sakit: flu").exists())

    def test_customer_cannot_cancel_someone_elses_booking(self):
        other = Customer.objects.create(name="Lain", phone_number="0819", address="x")
        booking = self.book(customer=other)
        self.client.login(username=self.customer.username, password="rahasia-123")
        r = self.client.post(reverse("service:cancel_my_booking", args=[booking.pk]), {"reason_note": "batal saja"})
        self.assertEqual(r.status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_booking_in_process_cannot_be_cancelled(self):
        booking = self.book()
        booking.check_in(self.kasir)
        booking.start(self.groomer)
        with self.assertRaises(InvalidBookingTransition):
            booking.cancel()

    def test_cashier_cancels_from_staff_page(self):
        booking = self.book()
        self.client.force_login(self.kasir)
        url = reverse("service:cancel_booking", args=[booking.pk])
        self.client.post(url)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.client.post(url, {"reason_choice": "lain", "reason_note": "Groomer sakit mendadak"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual((booking.cancel_reason, booking.cancelled_by), ("Groomer sakit mendadak", self.kasir))
        self.assertTrue(Notification.objects.filter(user=self.customer, body="Groomer sakit mendadak").exists())
        panel = self.client.get(reverse("service:manage_bookings") + f"?day={booking.schedule.date()}&id={booking.pk}")
        self.assertContains(panel, "Groomer sakit mendadak")

    def test_cancelled_booking_is_hidden_from_groomer_queue(self):
        booking = self.book()
        booking.cancel()
        self.client.force_login(self.groomer)
        r = self.client.get(reverse("service:groomer_dashboard"))
        self.assertNotIn(booking, r.context["bookings"])


    def test_only_first_queue_card_gets_primary_button(self):
        first, second = self.book(), self.book(customer=Customer.objects.create(name="Dua", phone_number="0818", address="x"))
        first.check_in(self.kasir)
        second.check_in(self.kasir)
        self.client.force_login(self.groomer)
        html = self.client.get(reverse("service:groomer_dashboard")).content.decode()
        self.assertEqual(html.count('class="btn-orange w-100"'), 1)
        self.assertEqual(html.count('class="g-btn-outline w-100"'), 1)
        self.assertLess(html.index("btn-orange w-100"), html.index("g-btn-outline w-100"))


class BookingCapacityTests(Fixtures, TestCase):
    def setUp(self):
        self.make_people()  # dua groomer aktif = dua booking bersamaan

    def test_online_booking_rejected_when_all_groomers_busy(self):
        when = tomorrow_at(10)
        self.book(schedule=when)
        self.book(schedule=when + timedelta(minutes=30))
        with self.assertRaises(InvalidBookingTransition):
            self.book(schedule=when + timedelta(minutes=15), check_capacity=True)
        # setelah durasi (60 menit) booking pertama selesai, slot terbuka lagi
        self.book(schedule=when + timedelta(minutes=60), check_capacity=True)

    def test_cancelled_booking_frees_the_slot(self):
        when = tomorrow_at(10)
        self.book(schedule=when)
        second = self.book(schedule=when)
        second.cancel()
        self.book(schedule=when, check_capacity=True)

    def test_staff_walk_in_is_not_blocked(self):
        when = tomorrow_at(10)
        for _ in range(3):
            self.book(schedule=when)
        self.assertEqual(ServiceBooking.objects.count(), 3)


class ClosingTimeTests(TestCase):
    def test_service_must_finish_before_closing(self):
        service = Service.objects.create(name="Grooming Lengkap", price=1, duration_minutes=120)
        late = tomorrow_at(19)
        form = BookingForm(
            {
                "service": service.pk,
                "pet_name": "Mochi",
                "pet_type": "KUCING",
                "schedule": late.strftime("%Y-%m-%dT%H:%M"),
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("schedule", form.errors)
        ok = BookingForm(
            {
                "service": service.pk,
                "pet_name": "Mochi",
                "pet_type": "KUCING",
                "schedule": tomorrow_at(17).strftime("%Y-%m-%dT%H:%M"),
            }
        )
        self.assertTrue(ok.is_valid(), ok.errors)
