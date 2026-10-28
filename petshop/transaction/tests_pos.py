"""Tes kasir (transaksi offline): bayar, diskon, shift, struk, parkir, batal, retur, laporan, scan."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import Customer, Role, User
from product.models import Category, Product
from store.models import StoreSettings

from . import pos
from .models import (
    Cart,
    CashierShift,
    Fulfillment,
    HeldSale,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ReturnStatus,
    ShiftStatus,
)


def make_product(name, stock=10, price=20000, sku=None):
    category, _created = Category.objects.get_or_create(name=Category.FOOD)
    return Product.objects.create(
        category=category, name=name, purchase_price=10000, selling_price=price, stock=stock, sku=sku
    )


class PosTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.cashier = User.objects.create_user("ksr", password="x", role=Role.CASHIER)
        self.p = make_product("Whiskas 1kg", stock=10, price=20000, sku="8990001")
        self.shift = pos.open_shift(self.cashier, 100000)

    def cart_with(self, user=None, qty=2, product=None):
        cart, _created = Cart.objects.get_or_create(user=user or self.cashier)
        cart.items.all().delete()  # sisa dari checkout yang ditolak
        cart.items.create(product=product or self.p, quantity=qty)
        return cart

    def sell(self, qty=2, **kwargs):
        user = kwargs.pop("user", self.cashier)
        kwargs.setdefault("cash_received", 20000 * qty)
        return pos.checkout(self.cart_with(user, qty), user, **kwargs)


class CheckoutRuleTests(PosTestCase):
    def test_walk_in_cash_sale_is_paid_and_done_with_change(self):
        order = self.sell(qty=2, cash_received=50000, buyer_name="Pak Budi")
        self.assertEqual(order.total_payment, 40000)
        self.assertEqual(order.change_given, 10000)
        self.assertEqual(order.payment_status, PaymentStatus.PAID)
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)
        self.assertEqual(order.status_display, "Selesai di kasir")
        self.assertTrue(order.customer.is_walk_in)
        self.assertTrue(order.receipt_no.startswith("STR-"))
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 8)
        self.assertFalse(Cart.objects.filter(user=self.cashier).exists())

    def test_walk_in_user_is_hidden_from_customer_lists(self):
        self.sell()
        self.assertFalse(Customer.objects.filter(is_walk_in=True).exists())
        self.assertFalse(User.customers().filter(is_walk_in=True).exists())

    def test_receipt_numbers_are_sequential_per_day(self):
        a = self.sell(qty=1)
        b = self.sell(qty=1)
        self.assertEqual(int(b.receipt_no[-4:]), int(a.receipt_no[-4:]) + 1)

    def test_cash_short_is_rejected_and_stock_untouched(self):
        with self.assertRaises(pos.PosError):
            self.sell(qty=2, cash_received=30000)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)
        self.assertEqual(Order.objects.count(), 0)

    def test_needs_open_shift(self):
        self.shift.close(100000)
        with self.assertRaises(pos.PosError):
            self.sell()

    def test_mixed_payment_needs_confirmation(self):
        with self.assertRaises(pos.PosError):
            self.sell(qty=2, pay_qris=15000, cash_received=25000)
        order = self.sell(qty=2, pay_qris=15000, pay_transfer=5000, cash_received=20000, noncash_confirmed=True)
        self.assertEqual(order.payment_method, PaymentMethod.MIXED)
        self.assertEqual(
            sorted((p.method, p.amount) for p in order.payments.all()),
            sorted([("TUNAI", 20000), ("QRIS", 15000), ("TRANSFER", 5000)]),
        )

    def test_full_qris_payment(self):
        order = self.sell(qty=1, pay_qris=20000, cash_received=0, noncash_confirmed=True)
        self.assertEqual(order.payment_method, PaymentMethod.QRIS)
        self.assertEqual(order.change_given, 0)

    def test_discount_needs_reason_and_admin_above_limit(self):
        with self.assertRaises(pos.PosError):
            self.sell(qty=2, discount=5000)
        order = self.sell(qty=2, discount=5000, discount_reason="Member lama", cash_received=35000)
        self.assertEqual(order.total_payment, 35000)
        self.assertEqual(order.discount_by, self.cashier)
        big = self.cart_with(qty=5)
        with self.assertRaises(pos.PosError):
            pos.checkout(big, self.cashier, discount=60000, discount_reason="Rusak", cash_received=40000)
        pos.open_shift(self.admin, 0)
        Cart.objects.filter(user=self.cashier).delete()
        order = pos.checkout(self.cart_with(self.admin, 5), self.admin, discount=60000,
                             discount_reason="Kemasan penyok", cash_received=40000)
        self.assertEqual(order.total_payment, 40000)

    def test_tax_is_added_after_discount(self):
        store = StoreSettings.current()
        store.tax_percent = Decimal("11")
        store.save()
        order = self.sell(qty=1, discount=1000, discount_reason="Promo", cash_received=21090)
        self.assertEqual(order.tax_amount, 2090)
        self.assertEqual(order.total_payment, 21090)

    def test_delivery_requires_registered_customer_with_address(self):
        with self.assertRaises(pos.PosError):
            self.sell(fulfillment=Fulfillment.DELIVERY)
        customer = Customer.objects.create(name="Rina", phone_number="081211112222", address="Jl. Mawar 1")
        Cart.objects.filter(user=self.cashier).delete()
        order = self.sell(qty=1, customer=customer, fulfillment=Fulfillment.DELIVERY,
                          shipping_fee=7000, cash_received=27000)
        self.assertEqual(order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(order.shipping_fee, 7000)
        self.assertIsNotNone(order.packing_seq)

    def test_delivery_uses_customer_home_pin_for_route_and_fee(self):
        from decimal import Decimal
        customer = Customer.objects.create(name="Rina", phone_number="081211112222", address="Jl. Mawar 1",
                                           latitude=Decimal("-0.510000"), longitude=Decimal("117.150000"))
        order = self.sell(qty=1, customer=customer, fulfillment=Fulfillment.DELIVERY, cash_received=10**7)
        self.assertEqual(order.delivery_latitude, Decimal("-0.510000"))
        self.assertIsNotNone(order.delivery_distance_km)
        self.assertGreater(order.shipping_fee, 0)  # ongkir dihitung dari jarak titik rumah

    def test_manual_order_paid_on_delivery_is_collected_by_courier(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        customer = Customer.objects.create(name="Rina", phone_number="081211112222", address="Jl. Mawar 1")
        with self.assertRaises(pos.PosError):  # COD hanya untuk diantar
            self.sell(qty=1, customer=customer, pay_on_delivery=True)
        order = self.sell(qty=1, customer=customer, fulfillment=Fulfillment.DELIVERY, shipping_fee=7000,
                          pay_on_delivery=True, cash_received=0, pay_qris=5000)
        self.assertEqual(order.total_payment, 27000)
        self.assertEqual(order.payment_method, PaymentMethod.CASH)
        self.assertEqual(order.payment_status, PaymentStatus.PENDING)
        self.assertFalse(order.payments.exists())
        self.assertEqual(self.shift.summary()["expected_cash"], 100000)  # uang belum masuk laci
        courier = User.objects.create_user("krr", password="x", role=Role.COURIER)
        Order.objects.filter(pk=order.pk).update(courier=courier, order_status=OrderStatus.ON_DELIVERY)
        order.refresh_from_db()
        photo = SimpleUploadedFile("p.jpg", b"x", content_type="image/jpeg")
        with self.assertRaises(Exception):  # kurir wajib konfirmasi uang tunai diterima
            order.handover(courier, order.handover_code, photo)
        order.handover(courier, order.handover_code, photo, cash_received=True)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, PaymentStatus.PAID)
        self.assertEqual(order.cash_collected, 27000)
        self.assertIn(order, Order.cash_on_hand(courier))

    def test_pay_on_delivery_screen_and_receipt(self):
        customer = Customer.objects.create(name="Rina", phone_number="081211112222", address="Jl. Mawar 1")
        self.client.force_login(self.cashier)
        self.cart_with(qty=1)
        page = self.client.get(reverse("transaction:make_transaction"))
        self.assertContains(page, 'name="pay_on_delivery" value="1"')
        r = self.client.post(reverse("transaction:submit_transaction"), {
            "customer": customer.pk, "fulfillment": "DIANTAR", "shipping_fee": "7000", "pay_on_delivery": "1",
        }, follow=True)
        self.assertContains(r, "Kurir menagih tunai")
        self.assertContains(r, "Belum dibayar, ditagih kurir")

    def test_manual_delivery_shares_handover_qr_link_with_buyer(self):
        customer = Customer.objects.create(name="Rina", phone_number="081211112222", address="Jl. Mawar 1")
        order = self.sell(qty=1, customer=customer, fulfillment=Fulfillment.DELIVERY, shipping_fee=7000,
                          pay_on_delivery=True)
        self.client.force_login(self.cashier)
        page = self.client.get(reverse("transaction:receipt", args=[order.pk]))
        self.assertContains(page, "QR serah-terima untuk pembeli")
        self.assertContains(page, "https://wa.me/6281211112222?text=")
        link = page.context["handover_link"]
        self.client.logout()
        track = reverse("customer:track_detail", args=[order.tracking_number])
        qr = reverse("customer:track_handover_qr", args=[order.tracking_number])
        # Resi saja (tertera di label paket) tidak membuka QR serah-terima.
        self.assertNotContains(self.client.get(track), order.handover_code)
        self.assertEqual(self.client.get(qr + "?k=salah").status_code, 404)
        # Tautan dari kasir bisa diteruskan ke orang lain: tetap minta 4 digit WA pembeli.
        r = self.client.get(link)
        self.assertNotContains(r, order.handover_code)
        self.assertContains(r, 'name="wa4"')
        self.assertEqual(self.client.get(qr + "?k=" + order.handover_key).status_code, 404)
        self.assertContains(self.client.post(link, {"wa4": "1111"}), "tidak cocok")
        r = self.client.post(link, {"wa4": "2222"}, follow=True)
        self.assertContains(r, order.handover_code)
        self.assertEqual(self.client.get(qr + "?k=" + order.handover_key).status_code, 200)
        # Bawa langsung: tidak ada QR serah-terima.
        take_away = self.sell(qty=1)
        self.client.force_login(self.cashier)
        self.assertNotContains(self.client.get(reverse("transaction:receipt", args=[take_away.pk])),
                               "QR serah-terima untuk pembeli")

    def test_grooming_paid_in_same_transaction(self):
        from service.models import BookingStatus, Service, ServiceBooking

        customer = Customer.objects.create(name="Dewi", phone_number="081299990000", address="x")
        service = Service.objects.create(name="Mandi kucing", price=50000)
        booking = ServiceBooking.objects.create(
            customer=customer, service=service, pet_name="Mochi", pet_type="KUCING",
            schedule=timezone.now(), price=50000, status=BookingStatus.READY,
        )
        cart = self.cart_with(qty=1)
        cart.add_service(booking)
        order = pos.checkout(cart, self.cashier, customer=customer, cash_received=70000)
        self.assertEqual(order.total_payment, 70000)
        self.assertEqual(order.service_lines.get().booking, booking)
        booking.refresh_from_db()
        self.assertTrue(booking.is_paid)
        with self.assertRaises(pos.PosError):
            Cart.objects.create(user=self.admin).add_service(booking)


class ShiftTests(PosTestCase):
    def test_expected_cash_and_difference_note(self):
        self.sell(qty=2, cash_received=50000)
        summary = self.shift.summary()
        self.assertEqual(summary["cash_sales"], 40000)
        self.assertEqual(summary["expected_cash"], 140000)
        with self.assertRaises(Exception):
            self.shift.close(135000)
        self.shift.close(135000, "Uang receh kurang")
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, ShiftStatus.CLOSED)
        self.assertEqual(self.shift.difference, -5000)

    def test_only_one_open_shift(self):
        with self.assertRaises(pos.PosError):
            pos.open_shift(self.cashier, 0)

    def test_voided_sale_is_not_expected_cash(self):
        order = self.sell(qty=1)
        pos.void(order, self.admin, "Salah input")
        self.assertEqual(self.shift.summary()["expected_cash"], 100000)


class HoldResumeTests(PosTestCase):
    def test_hold_then_resume(self):
        cart = self.cart_with(qty=3)
        held = pos.hold(cart, self.cashier, "Bu Rina")
        self.assertTrue(Cart.objects.get(pk=cart.pk).is_empty)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)  # stok baru berkurang saat dibayar
        warnings = pos.resume(held, self.cashier)
        self.assertEqual(warnings, [])
        self.assertEqual(Cart.objects.get(user=self.cashier).items.get().quantity, 3)
        self.assertFalse(HeldSale.objects.exists())

    def test_resume_caps_to_stock(self):
        held = pos.hold(self.cart_with(qty=5), self.cashier)
        self.p.stock = 2
        self.p.save()
        warnings = pos.resume(held, self.cashier)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(Cart.objects.get(user=self.cashier).items.get().quantity, 2)


class VoidAndReturnTests(PosTestCase):
    def test_void_is_admin_only_with_reason_and_restores_stock(self):
        order = self.sell(qty=2)
        with self.assertRaises(Exception):
            pos.void(order, self.cashier, "x")
        with self.assertRaises(Exception):
            pos.void(order, self.admin, "")
        pos.void(order, self.admin, "Pembeli batal")
        order.refresh_from_db()
        self.assertTrue(order.is_voided)
        self.assertEqual(order.voided_by, self.admin)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)

    def test_return_flow_proportional_refund(self):
        order = self.sell(qty=2, discount=4000, discount_reason="Promo", cash_received=36000)
        detail = order.details.get()
        req = pos.request_return(order, self.cashier, {detail.pk: 1}, "Kemasan bocor")
        self.assertEqual(req.refund_amount, 18000)  # 20.000 x (36.000 / 40.000)
        self.assertEqual(pos.returnable_qty(detail), 1)
        with self.assertRaises(Exception):
            pos.decide_return(req, self.cashier, True)
        pos.decide_return(req, self.admin, True)
        req.refresh_from_db()
        self.assertEqual(req.status, ReturnStatus.APPROVED)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 9)
        self.assertEqual(self.shift.summary()["refunds"], 18000)

    def test_return_rejected_needs_note_and_keeps_stock(self):
        order = self.sell(qty=1)
        req = pos.request_return(order, self.cashier, {order.details.get().pk: 1}, "Tidak suka")
        with self.assertRaises(Exception):
            pos.decide_return(req, self.admin, False, "")
        pos.decide_return(req, self.admin, False, "Barang sudah dibuka")
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 9)

    def test_return_window(self):
        order = self.sell(qty=1)
        Order.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timezone.timedelta(days=8))
        order.refresh_from_db()
        self.assertFalse(pos.can_return(order))
        with self.assertRaises(pos.PosError):
            pos.request_return(order, self.cashier, {order.details.get().pk: 1}, "Rusak")

    def test_cannot_void_after_return(self):
        order = self.sell(qty=1)
        pos.request_return(order, self.cashier, {order.details.get().pk: 1}, "Rusak")
        with self.assertRaises(Exception):
            pos.void(order, self.admin, "Batal")


class PosViewTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="ksr", password="x")

    def test_screen_shows_shift_and_scan(self):
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertContains(r, "Kasir buka")
        self.assertContains(r, 'name="code"')
        # Kolom pembeli & bayar baru muncul setelah ada barang di keranjang.
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        self.assertContains(self.client.get("/staff/admin/make_transaction/"), "Pelanggan umum")

    def test_screen_shows_auto_shipping_fee_before_pay(self):
        """Ongkir otomatis yang ditagih saat Bayar sudah terlihat di layar kasir (mis. untuk 'Uang pas')."""
        customer = Customer.objects.create(name="Rina", phone_number="081211112222", address="Jl. Mawar 1",
                                           latitude=Decimal("-0.510000"), longitude=Decimal("117.150000"))
        store = StoreSettings.current()
        fee = store.shipping_fee(store.distance_km(customer.latitude, customer.longitude))
        self.assertGreater(fee, 0)
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertContains(r, f'value="{customer.pk}" data-ship="{fee}"')
        order = pos.checkout(Cart.objects.get(user=self.cashier), self.cashier, customer=customer,
                             fulfillment=Fulfillment.DELIVERY, cash_received=20000 + fee)
        self.assertEqual(order.shipping_fee, fee)

    def test_cashier_adds_new_customer_for_delivery(self):
        """Kasir bisa mendaftarkan pelanggan baru sendiri (tanpa admin) lalu langsung mengantar pesanannya."""
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        self.assertContains(self.client.get("/staff/admin/make_transaction/"), "data-qc-open")
        r = self.client.post(reverse("transaction:quick_customer"), {
            "name": "Budi Santoso", "phone_number": "0812 3333 4444", "address": "Jl. Kenari 5",
            "latitude": "-0.510000", "longitude": "117.150000",
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        customer = Customer.objects.get(pk=data["pk"])
        self.assertEqual(customer.name, "Budi Santoso")
        self.assertFalse(customer.has_usable_password())  # belum bisa login sampai daftar sendiri
        self.assertGreater(data["ship"], 0)
        order = pos.checkout(Cart.objects.get(user=self.cashier), self.cashier, customer=customer,
                             fulfillment=Fulfillment.DELIVERY, cash_received=20000 + data["ship"])
        self.assertEqual(order.shipping_fee, data["ship"])
        # Nomor yang sama tidak boleh dobel; alamat wajib.
        r = self.client.post(reverse("transaction:quick_customer"), {
            "name": "Budi Lain", "phone_number": "081233334444", "address": "",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("phone_number", r.json()["errors"])
        self.assertIn("address", r.json()["errors"])

    def test_quick_customer_is_for_pos_roles_only(self):
        User.objects.create_user("kur", password="x", role=Role.COURIER)
        self.client.login(username="kur", password="x")
        r = self.client.post(reverse("transaction:quick_customer"), {"name": "X", "phone_number": "0811", "address": "Y"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Customer.objects.filter(first_name="X").exists())

    def test_phone_pay_bar_shows_only_with_items(self):
        self.assertNotContains(self.client.get("/staff/admin/make_transaction/"), "data-paybar-total")
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertContains(r, "data-paybar-total")
        self.assertContains(r, 'href="#posPayment"')

    def test_category_chip_filters_products(self):
        toy = Product.objects.create(
            category=Category.objects.get_or_create(name=Category.TOYS)[0], name="Bola Karet", purchase_price=5000,
            selling_price=9000, stock=5,
        )
        r = self.client.get(f"/staff/admin/make_transaction/?cat={toy.category_id}")
        self.assertContains(r, "Bola Karet")
        self.assertNotContains(r, "Whiskas 1kg")
        self.assertContains(r, 'aria-current="true">Mainan</a>', html=False)
        r = self.client.get("/staff/admin/make_transaction/?cat=abc")
        self.assertContains(r, "Whiskas 1kg")

    def test_plus_minus_buttons_change_quantity(self):
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        item = Cart.objects.get(user=self.cashier).items.get()
        url = f"/staff/admin/cart/update/{item.pk}/"
        self.client.post(url, {"step": "1", "quantity": "1"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.client.post(url, {"step": "-1", "quantity": "2"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)
        self.client.post(url, {"quantity": "4"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)

    def test_pay_fields_hidden_until_cart_has_items(self):
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertNotContains(r, 'name="cash_received"')
        self.assertContains(r, "Keranjang masih kosong")
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertContains(r, 'name="cash_received"')
        self.assertContains(r, "data-pay-total")

    def test_sidebar_shows_shift_status(self):
        r = self.client.get("/staff/kasir/")
        self.assertContains(r, "staff-shift is-open")
        CashierShift.objects.filter(pk=self.shift.pk).update(status=ShiftStatus.CLOSED)
        r = self.client.get("/staff/kasir/")
        self.assertContains(r, "staff-shift is-closed")
        self.assertContains(r, "Kasir belum dibuka")

    def test_scan_sku_adds_product(self):
        self.client.post("/staff/admin/kasir/scan/", {"code": " 8990001 "})
        self.assertEqual(Cart.objects.get(user=self.cashier).items.get().product, self.p)
        r = self.client.post("/staff/admin/kasir/scan/", {"code": "TIDAKADA"}, follow=True)
        self.assertContains(r, "tidak dikenal")

    def test_submit_prints_receipt_and_public_receipt_works(self):
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        r = self.client.post("/staff/admin/cart/submit/", {"cash_received": "50.000", "buyer_phone": "0812 3456"})
        order = Order.objects.get()
        self.assertRedirects(r, f"/staff/admin/transaction/{order.pk}/struk/?print=1", fetch_redirect_response=False)
        r = self.client.get(f"/staff/admin/transaction/{order.pk}/struk/?print=1")
        self.assertContains(r, order.receipt_no)
        self.assertContains(r, "data-auto-print")
        self.assertContains(r, "30.000")  # kembalian
        self.assertNotContains(r, "Batalkan transaksi")  # kasir tidak bisa membatalkan
        self.client.logout()
        r = self.client.get(f"/struk/{order.receipt_token}/")
        self.assertContains(r, order.receipt_no)
        self.assertEqual(r["X-Robots-Tag"], "noindex")
        self.assertEqual(self.client.get(f"/struk/{order.receipt_token}/qr.svg").status_code, 200)
        self.assertEqual(self.client.get("/struk/salah/").status_code, 404)

    def test_hold_from_screen(self):
        self.client.post("/staff/admin/kasir/scan/", {"code": "8990001"})
        self.client.post("/staff/admin/kasir/parkir/", {"label": "Meja 2"})
        held = HeldSale.objects.get()
        self.assertEqual(held.label, "Meja 2")
        self.client.post(f"/staff/admin/kasir/parkir/{held.pk}/", {"action": "resume"})
        self.assertFalse(HeldSale.objects.exists())

    def test_cashier_cannot_void_or_open_report(self):
        order = self.sell(qty=1)
        self.client.post(f"/staff/admin/transaction/{order.pk}/batal/", {"reason": "x"})
        order.refresh_from_db()
        self.assertFalse(order.is_voided)
        self.assertNotEqual(self.client.get("/staff/admin/laporan-kasir/").status_code, 200)

    def test_old_cancel_action_refuses_counter_sale(self):
        order = self.sell(qty=1, fulfillment=Fulfillment.TAKE_AWAY)
        self.client.login(username="adm", password="x")
        self.client.post(f"/staff/admin/transaction/{order.pk}/status/", {"action": "cancel"})
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, OrderStatus.CANCELLED)

    def test_shift_page_close(self):
        r = self.client.get("/staff/kasir/shift/")
        self.assertContains(r, "Seharusnya ada")
        self.client.post("/staff/kasir/shift/", {"action": "close", "amount": "100000"})
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, ShiftStatus.CLOSED)
        self.assertEqual(self.client.get("/staff/kasir/shift/").status_code, 200)

    def test_return_pages(self):
        order = self.sell(qty=2)
        detail = order.details.get()
        self.assertContains(self.client.get(f"/staff/admin/transaction/{order.pk}/retur/"), "Ajukan retur")
        self.client.post(f"/staff/admin/transaction/{order.pk}/retur/",
                         {f"qty_{detail.pk}": "1", "reason": "Rusak", "refund_method": "TUNAI"})
        req = order.returns.get()
        self.assertContains(self.client.get("/staff/admin/retur/"), "Rusak")
        self.client.login(username="adm", password="x")
        self.client.post(f"/staff/admin/retur/{req.pk}/putuskan/", {"decision": "approve"})
        req.refresh_from_db()
        self.assertEqual(req.status, ReturnStatus.APPROVED)


class ReportTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="adm", password="x")

    def test_report_page_and_csv(self):
        self.sell(qty=1)
        self.sell(qty=1, pay_qris=20000, cash_received=0, noncash_confirmed=True)
        r = self.client.get("/staff/admin/laporan-kasir/?range=1")
        self.assertContains(r, "Laporan Kasir")
        report = r.context["report"]
        totals = {m["code"]: m["total"] for m in report["by_method"]}
        self.assertEqual(totals["TUNAI"], 20000)
        self.assertEqual(totals["QRIS"], 20000)
        self.assertEqual(report["channel"]["offline"]["total"], 40000)
        csv = self.client.get("/staff/admin/laporan-kasir/?range=1&format=csv")
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("STR-", csv.content.decode("utf-8"))

    def test_report_summary_daily_and_shares(self):
        self.sell(qty=1)
        self.sell(qty=2)
        r = self.client.get("/staff/admin/laporan-kasir/?range=7")
        report = r.context["report"]
        self.assertEqual(report["total_in"], 60000)
        self.assertEqual(report["avg_offline"], 30000)
        days = report["daily"]["days"]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1]["day"], timezone.localdate())
        self.assertEqual(sum(d["total"] for d in days), 60000)
        self.assertEqual(days[-1]["pct"], 100)
        self.assertEqual({m["code"]: m["pct"] for m in report["by_method"]}["TUNAI"], 100)
        self.assertContains(r, "Total uang masuk")
        self.assertContains(r, "Rp 60.000")

    def test_product_codes_generated(self):
        bare = make_product("Pasir kucing")
        self.client.post("/staff/admin/produk/kode-barang/")
        bare.refresh_from_db()
        self.assertEqual(bare.sku, f"SLY-{bare.pk:04d}")
        self.assertContains(self.client.get("/staff/admin/produk/kode-barang/"), bare.sku)
        self.assertEqual(self.client.get(f"/staff/admin/produk/{bare.pk}/kode.svg").status_code, 200)


class CashierHomeTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="ksr", password="x")

    def test_cashier_lands_on_home_with_shift_money_split(self):
        self.sell(qty=1, cash_received=20000)
        self.sell(qty=2, cash_received=0, pay_qris=40000, noncash_confirmed=True)
        self.assertEqual(self.shift.summary()["noncash_sales"], 40000)
        r = self.client.get("/staff/kasir/")
        self.assertContains(r, "Buka layar kasir")
        self.assertContains(r, "Rp 40.000")  # transfer + QRIS
        self.assertContains(r, "Rp 120.000")  # modal 100.000 + tunai 20.000
        self.assertContains(r, "Struk terakhir Anda")

    def test_home_without_shift_asks_to_open(self):
        self.shift.close(100000)
        r = self.client.get("/staff/kasir/")
        self.assertContains(r, "Kasir belum dibuka")
        self.assertNotContains(r, "Buka layar kasir")

    def test_other_roles_cannot_open_cashier_home(self):
        User.objects.create_user("grm", password="x", role=Role.GROOMER)
        self.client.login(username="grm", password="x")
        self.assertNotEqual(self.client.get("/staff/kasir/").status_code, 200)


class DashboardHelperTests(PosTestCase):
    def test_change_compares_with_previous_period(self):
        from account.dashboard import change

        self.assertEqual(change(150, 100), {"dir": "up", "pct": 50, "diff": 50})
        self.assertEqual(change(50, 100)["dir"], "down")
        self.assertEqual(change(100, 100)["dir"], "flat")
        self.assertIsNone(change(10, 0)["pct"])  # tidak ada pembanding: persen tidak dikarang

    def test_tasks_only_list_waiting_work(self):
        from account.dashboard import staff_tasks

        labels = [t["label"] for t in staff_tasks(self.cashier)]
        self.assertNotIn("Pesanan online menunggu konfirmasi", labels)
        self.assertNotIn("Produk stok menipis", labels)  # khusus admin
        make_product("Hampir habis", stock=1)
        labels = [t["label"] for t in staff_tasks(self.admin)]
        self.assertIn("Produk stok menipis", labels)
