"""Tes untuk perbaikan hasil audit: snapshot alamat, anti pesanan ganda,
validasi total di server, pembatalan berulang, dan endpoint cek keranjang."""

import json

from django.test import TestCase
from django.urls import reverse

from account.models import Customer, Role, User
from product.models import StockMutation
from store.models import BankAccount, Notification

from .models import (
    Cart,
    CartItem,
    InvalidTransition,
    Order,
    OrderStatus,
    PriceChanged,
)
from .tests import make_product


class OnlineOrderIntegrityTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Siti", phone_number="081300000001", address="Jl. Lama 1"
        )
        self.customer.set_password("rahasia-123")
        self.customer.save()
        self.a = make_product("Whiskas", stock=10, price=20000)

    def place(self, **kw):
        data = dict(lines=[(self.a.pk, 2)], payment_method="TUNAI")
        data.update(kw)
        return Order.place_online(self.customer, **data)

    def test_shipping_address_is_a_snapshot(self):
        order = self.place(address="Jl. Kirim 9")
        self.customer.address = "Jl. Baru 2"
        self.customer.save()
        order.refresh_from_db()
        self.assertEqual(order.shipping_address, "Jl. Kirim 9")
        self.assertEqual(order.delivery_address, "Jl. Kirim 9")

    def test_same_client_token_returns_same_order_and_moves_stock_once(self):
        first = self.place(client_token="tok-1")
        second = self.place(client_token="tok-1")
        self.assertEqual(first.pk, second.pk)
        self.assertTrue(getattr(second, "replayed", False))
        self.assertEqual(Order.objects.count(), 1)
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 8)

    def test_expected_total_mismatch_rolls_back_everything(self):
        with self.assertRaises(PriceChanged) as caught:
            self.place(expected_total=30000)  # pelanggan melihat harga lama
        self.assertEqual(caught.exception.total, 40000)
        self.assertEqual(Order.objects.count(), 0)
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        self.assertEqual(StockMutation.objects.filter(product=self.a).count(), 0)

    def test_expected_total_match_is_accepted(self):
        order = self.place(expected_total=40000)
        self.assertEqual(order.total_payment, 40000)

    def test_place_order_view_reports_price_change_with_409(self):
        self.client.login(username=self.customer.username, password="rahasia-123")
        body = {
            "items": [{"id": self.a.pk, "quantity": 1}],
            "payment_method": "TUNAI",
            "address": "Jl. Kirim 9",
            "latitude": "-1.265400",
            "longitude": "116.831200",
            "expected_total": 1000,
            "client_token": "abc",
        }
        r = self.client.post(
            reverse("customer:place_order"),
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["reason"], "price_changed")
        body["expected_total"] = 25000  # barang 20.000 + ongkir dasar 5.000
        r = self.client.post(
            reverse("customer:place_order"),
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post(
            reverse("customer:place_order"),
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(r.json()["order_id"], r2.json()["order_id"])
        self.assertEqual(Order.objects.count(), 1)

    def test_cancel_twice_restores_stock_once(self):
        order = self.place()
        order.cancel()
        stale = Order.objects.get(pk=order.pk)
        stale.order_status = OrderStatus.CONFIRMED  # salinan lama di memori
        with self.assertRaises(InvalidTransition):
            stale.cancel()
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)

    def test_customer_cannot_cancel_after_store_confirmed(self):
        order = self.place()
        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        Order.objects.get(pk=order.pk).confirm(admin)
        self.client.login(username=self.customer.username, password="rahasia-123")
        self.client.post(reverse("customer:cancel_my_order", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)

    def test_pos_checkout_copies_customer_address(self):
        admin = User.objects.create_user("kasir", password="x", role=Role.CASHIER)
        cart = Cart.objects.create(user=admin)
        CartItem.objects.create(cart=cart, product=self.a, quantity=1)
        order = cart.checkout(customer=self.customer, admin=admin, payment_method="TUNAI")
        self.assertEqual(order.shipping_address, "Jl. Lama 1")


class CartCheckEndpointTests(TestCase):
    def test_returns_current_price_stock_and_unavailable_items(self):
        a = make_product("A", stock=3, price=12000)
        hidden = make_product("B", stock=5)
        hidden.is_active = False
        hidden.save()
        r = self.client.get(reverse("customer:cart_check"), {"ids": f"{a.pk},{hidden.pk},999"})
        items = {row["id"]: row for row in r.json()["items"]}
        self.assertEqual(items[a.pk]["price"], 12000)
        self.assertEqual(items[a.pk]["stock"], 3)
        self.assertTrue(items[a.pk]["available"])
        self.assertFalse(items[hidden.pk]["available"])
        self.assertFalse(items[999]["available"])

    def test_out_of_stock_is_unavailable(self):
        a = make_product("A", stock=0)
        r = self.client.get(reverse("customer:cart_check"), {"ids": str(a.pk)})
        self.assertFalse(r.json()["items"][0]["available"])


class ManualTransferInstructionTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Siti", phone_number="081300000001", address="Jl. Lama 1"
        )
        self.customer.set_password("rahasia-123")
        self.customer.save()
        self.client.login(username=self.customer.username, password="rahasia-123")
        self.a = make_product("Whiskas", stock=10, price=20000)

    def order(self, method="TRANSFER"):
        return Order.place_online(self.customer, lines=[(self.a.pk, 1)], payment_method=method)

    def test_unpaid_transfer_shows_bank_and_proof_link(self):
        from store.models import BankAccount

        BankAccount.objects.create(bank="BCA", number="1234567890", holder="Seelly Petshop")
        order = self.order()
        r = self.client.get(reverse("customer:my_orders"))
        self.assertContains(r, "1234567890")
        self.assertContains(r, "Kirim Bukti Transfer")
        self.assertContains(r, f"pesanan%20%23{order.pk}")

    def test_without_accounts_customer_is_told_admin_sends_them(self):
        self.order()
        r = self.client.get(reverse("customer:my_orders"))
        self.assertContains(r, "Nomor rekening dikirim admin lewat WhatsApp")

    def test_paid_or_cash_orders_hide_instructions(self):
        paid = self.order()
        paid.mark_paid()
        self.order(method="TUNAI")
        r = self.client.get(reverse("customer:my_orders"))
        self.assertNotContains(r, "Kirim Bukti Transfer")


class RichDemoDataTests(TestCase):
    def test_seed_fills_every_module_with_detail(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        from courier.models import CourierLocation
        from product.models import Product
        from service.models import BookingStatus, ServiceBooking

        with override_settings(DEBUG=True):
            call_command("seed_demo", orders=60, no_photos=True, stdout=StringIO())
        self.assertFalse(Product.objects.filter(description="").exists())
        self.assertFalse(Customer.objects.filter(email="").exists())
        self.assertTrue(Order.objects.filter(channel="ONLINE").exists())
        self.assertTrue(Order.objects.filter(channel="TOKO").exists())
        self.assertTrue(
            ServiceBooking.objects.filter(status=BookingStatus.CANCELLED).exists()
        )
        self.assertTrue(
            Order.objects.filter(
                customer__username="demo_customer",
                payment_method="TRANSFER",
                payment_status="MENUNGGU",
            ).exists()
        )
        # Hanya Super Admin demo yang bisa membuka /admin/; Admin biasa tidak.
        self.assertTrue(User.objects.get(username="demo_superadmin").is_superuser)
        self.assertFalse(User.objects.get(username="demo_admin").is_superuser)
        self.assertTrue(BankAccount.objects.exists())
        self.assertTrue(Notification.objects.filter(user__username="demo_customer").exists())
        if Order.objects.filter(order_status="DALAM_PENGIRIMAN").exists():
            self.assertTrue(CourierLocation.objects.exists())
        call_command("audit_stock", stdout=StringIO())

    def test_seed_feature_accounts_cover_every_status(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        from service.models import BookingStatus, ServiceBooking
        from store.models import Complaint, StoreSettings

        with override_settings(DEBUG=True):
            call_command("seed_demo", orders=30, no_photos=True, stdout=StringIO())
            call_command("seed_demo", orders=30, no_photos=True, stdout=StringIO())  # aman dijalankan ulang
        self.assertIn("Ery Suparjan", StoreSettings.current().address)
        orders = Order.objects.filter(customer__username="demo_belanja")
        self.assertEqual(
            set(orders.values_list("order_status", flat=True)),
            {"MENUNGGU", "DIKONFIRMASI", "DALAM_PENGIRIMAN", "TERKIRIM", "DIBATALKAN"},
        )
        self.assertTrue(orders.exclude(payment_proof="").exists())
        self.assertTrue(orders.exclude(payment_reject_note="").exists())
        self.assertTrue(orders.filter(rating__isnull=False).exists())
        bookings = ServiceBooking.objects.filter(customer__username="demo_grooming")
        self.assertTrue({
            BookingStatus.PENDING, BookingStatus.SCHEDULED, BookingStatus.QUEUED, BookingStatus.PROCESS,
            BookingStatus.READY, BookingStatus.DONE, BookingStatus.CANCELLED,
        } <= set(bookings.values_list("status", flat=True)))
        self.assertEqual(
            set(Complaint.objects.filter(customer__username="demo_komplain").values_list("status", flat=True)),
            {"BARU", "DIPROSES", "SELESAI"},
        )
        self.assertTrue(Complaint.objects.filter(customer__username="demo_customer").exists())
        for username in ("demo_customer", "demo_belanja", "demo_grooming", "demo_komplain"):
            self.assertTrue(Notification.objects.filter(user__username=username).exists(), username)

    def test_admin_site_lists_orders_read_only(self):
        admin = User.objects.create_superuser("root", password="x", role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertEqual(self.client.get("/admin/transaction/order/").status_code, 200)
        self.assertEqual(self.client.get("/admin/transaction/order/add/").status_code, 403)
        self.assertEqual(self.client.get("/admin/product/stockmutation/").status_code, 200)
