from django.urls import reverse
from django.test import TestCase
from account.models import User, Customer, Role
from django.test import SimpleTestCase
from transaction.models import PaymentMethod, PAYMENT_REGISTRY
from product.models import Category, Product, StockMutation, InsufficientStock
from .models import (
    Cart,
    CartItem,
    Order,
    OrderStatus,
    PaymentStatus,
    CheckoutError,
    InvalidTransition,
)


def make_product(name, stock, price=15000):
    category, _ = Category.objects.get_or_create(name=Category.FOOD)
    return Product.objects.create(
        category=category,
        name=name,
        purchase_price=10000,
        selling_price=price,
        stock=stock,
    )


class CheckoutTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.courier = User.objects.create_user("cr", password="x", role=Role.COURIER)
        self.customer = Customer.objects.create(
            name="Budi", phone_number="08", address="x"
        )
        self.cart = Cart.objects.create(user=self.admin)
        self.a = make_product("A", stock=5)
        self.b = make_product("B", stock=1)

    def checkout(self, **kw):
        return self.cart.checkout(
            customer=self.customer, admin=self.admin, payment_method="TUNAI", **kw
        )

    def test_cart_total(self):
        CartItem.objects.create(cart=self.cart, product=self.a, quantity=2)
        self.assertEqual(self.cart.total, 30000)

    def test_checkout_creates_order_details_mutations_and_clears_cart(self):
        CartItem.objects.create(cart=self.cart, product=self.a, quantity=2)
        order = self.checkout(courier=self.courier)
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 3)
        self.assertEqual(order.total_payment, 30000)
        self.assertEqual(order.details.count(), 1)
        self.assertEqual(StockMutation.objects.filter(product=self.a).count(), 1)
        self.assertFalse(Cart.objects.filter(pk=self.cart.pk).exists())

    def test_checkout_without_courier_ok(self):
        CartItem.objects.create(cart=self.cart, product=self.a, quantity=1)
        self.assertIsNone(self.checkout().courier)

    def test_second_item_fails_rolls_back_first(self):
        CartItem.objects.create(cart=self.cart, product=self.a, quantity=2)
        CartItem.objects.create(cart=self.cart, product=self.b, quantity=9)
        with self.assertRaises(InsufficientStock):
            self.checkout()
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 5)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockMutation.objects.count(), 0)
        self.assertTrue(Cart.objects.filter(pk=self.cart.pk).exists())

    def test_empty_cart_raises(self):
        with self.assertRaises(CheckoutError):
            self.checkout()


class OrderStatusTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.courier = User.objects.create_user("cr", password="x", role=Role.COURIER)
        customer = Customer.objects.create(name="Budi", phone_number="08", address="x")
        self.p = make_product("A", stock=5)
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=self.p, quantity=2)
        self.order = cart.checkout(
            customer=customer, admin=self.admin, payment_method="TUNAI"
        )

    def test_new_order_is_confirmed_and_unpaid(self):
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    def test_detail_snapshots_unit_price(self):
        detail = self.order.details.get()
        self.p.selling_price = 99999
        self.p.save()
        detail.refresh_from_db()
        self.assertEqual(detail.unit_price, 15000)
        self.assertEqual(detail.subtotal, 30000)

    def test_on_delivery_needs_courier(self):
        with self.assertRaises(InvalidTransition):
            self.order.mark_on_delivery()
        self.order.mark_on_delivery(self.courier)
        self.assertEqual(self.order.order_status, OrderStatus.ON_DELIVERY)
        self.assertEqual(self.order.courier, self.courier)

    def test_cash_delivered_marks_paid(self):
        self.order.mark_delivered()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_transfer_delivered_stays_pending_until_paid(self):
        self.order.payment_method = "TRANSFER"
        self.order.save()
        self.order.mark_delivered()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)
        self.order.mark_paid()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_cancel_restores_stock_once(self):
        self.order.cancel()
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)
        with self.assertRaises(InvalidTransition):
            self.order.cancel()
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)

    def test_cannot_pay_cancelled_or_reopen_delivered(self):
        self.order.cancel()
        with self.assertRaises(InvalidTransition):
            self.order.mark_paid()

    def test_delivered_is_final(self):
        self.order.mark_delivered()
        with self.assertRaises(InvalidTransition):
            self.order.cancel()
        with self.assertRaises(InvalidTransition):
            self.order.mark_on_delivery(self.courier)


class CartQuantityTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.cart = Cart.objects.create(user=admin)
        self.p = make_product("A", stock=5)
        self.item = CartItem.objects.create(cart=self.cart, product=self.p, quantity=1)

    def test_set_quantity(self):
        self.cart.set_quantity(self.item.pk, 4)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 4)

    def test_over_stock_rejected(self):
        with self.assertRaises(InsufficientStock):
            self.cart.set_quantity(self.item.pk, 6)

    def test_zero_removes_item(self):
        self.cart.set_quantity(self.item.pk, 0)
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.customer = Customer.objects.create(
            name="Budi", phone_number="08", address="x"
        )
        self.p = make_product("A", stock=3)
        self.client.login(username="adm", password="x")

    def test_make_transaction_page_loads(self):
        User.objects.create_user("cr", password="x", role=Role.COURIER)
        self.assertEqual(
            self.client.get("/staff/admin/make_transaction/").status_code, 200
        )

    def test_add_then_submit(self):
        self.client.post("/staff/kasir/shift/", {"action": "open", "amount": "0"})
        self.client.post(f"/staff/admin/cart/add/{self.p.pk}/")
        self.client.post(f"/staff/admin/cart/add/{self.p.pk}/")
        self.client.post(
            "/staff/admin/cart/submit/",
            {"customer": self.customer.pk, "cash_received": "30000", "courier": ""},
        )
        order = Order.objects.get()
        self.assertEqual(order.total_payment, 30000)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 1)

    def test_login_redirects_to_dashboard(self):
        self.client.logout()
        r = self.client.post("/login", {"username": "adm", "password": "x"})
        self.assertRedirects(r, "/staff/admin/dashboard", fetch_redirect_response=False)


class ManageTransactionViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.courier = User.objects.create_user("cr", password="x", role=Role.COURIER)
        customer = Customer.objects.create(name="Budi", phone_number="08", address="x")
        self.p = make_product("A", stock=5)
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=self.p, quantity=2)
        self.order = cart.checkout(
            customer=customer, admin=self.admin, payment_method="TUNAI"
        )
        self.client.login(username="adm", password="x")

    def act(self, action, **extra):
        return self.client.post(
            f"/staff/admin/transaction/{self.order.pk}/status/",
            {"action": action, **extra},
        )

    def test_list_page_renders_with_orders(self):
        r = self.client.get("/staff/admin/manage_transaction/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, f"Order #{self.order.pk}")

    def test_modal_shows_resi_and_whatsapp_share_link(self):
        r = self.client.get("/staff/admin/manage_transaction/")
        self.assertContains(r, self.order.tracking_number)
        self.assertContains(r, "Kirim Resi ke Pelanggan")
        # Link lacak ikut di dalam teks WhatsApp (ter-encode di parameter ?text=).
        self.assertContains(r, f"//testserver/lacak/{self.order.tracking_number}/")

    def test_search_by_resi(self):
        hit = self.client.get(
            "/staff/admin/manage_transaction/",
            {"view": "list", "q": self.order.tracking_number[-6:]},
        )
        self.assertContains(hit, f"Order #{self.order.pk}")
        miss = self.client.get(
            "/staff/admin/manage_transaction/", {"view": "list", "q": "ZZZZZZ"}
        )
        self.assertNotContains(miss, f"Order #{self.order.pk}")

    def test_modal_says_when_closed_without_photo(self):
        self.order.mark_on_delivery(self.courier)
        self.act("delivered")
        r = self.client.get("/staff/admin/manage_transaction/")
        self.assertContains(r, "Tidak ada foto bukti")

    def test_full_flow(self):
        # Admin hanya menugaskan kurir; kurir yang mulai mengirim.
        self.act("assign_courier", courier=self.courier.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)
        self.assertEqual(self.order.courier, self.courier)
        self.order.mark_on_delivery(self.courier)
        self.act("delivered")
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.DELIVERED)
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_admin_cannot_dispatch(self):
        self.act("on_delivery", courier=self.courier.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)

    def test_assign_courier_without_courier_rejected(self):
        self.act("assign_courier")
        self.order.refresh_from_db()
        self.assertIsNone(self.order.courier)

    def test_cash_order_can_get_courier_before_paid(self):
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)
        self.act("assign_courier", courier=self.courier.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.courier, self.courier)

    def test_transfer_needs_paid_before_courier(self):
        self.order.payment_method = "TRANSFER"
        self.order.save(update_fields=["payment_method"])
        self.act("assign_courier", courier=self.courier.pk)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.courier)
        self.act("paid")
        self.act("assign_courier", courier=self.courier.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.courier, self.courier)

    def test_courier_cannot_start_unpaid_transfer(self):
        self.order.payment_method = "TRANSFER"
        self.order.save(update_fields=["payment_method"])
        with self.assertRaises(InvalidTransition):
            self.order.mark_on_delivery(self.courier)

    def test_cancel_via_view_restores_stock(self):
        self.act("cancel")
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)

    def test_update_cart_quantity_view(self):
        cart = Cart.objects.create(user=self.admin)
        item = CartItem.objects.create(cart=cart, product=self.p, quantity=1)
        self.client.post(f"/staff/admin/cart/update/{item.pk}/", {"quantity": "3"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)


class CustomerSelectionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.p = make_product("A", stock=5)
        self.client.login(username="adm", password="x")
        self.client.post("/staff/kasir/shift/", {"action": "open", "amount": "0"})
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=self.p, quantity=1)

    def submit(self, **data):
        return self.client.post(
            "/staff/admin/cart/submit/", {"cash_received": "15000", **data}
        )

    def test_selected_customer_used(self):
        c = Customer.objects.create(
            name="Budi", phone_number="081234567890", address="x"
        )
        self.submit(customer=c.pk)
        self.assertEqual(Order.objects.get().customer, c)

    def test_no_customer_becomes_walk_in_buyer(self):
        self.submit(buyer_name="Ibu berbaju merah")
        order = Order.objects.get()
        self.assertTrue(order.customer.is_walk_in)
        self.assertEqual(order.buyer_display, "Ibu berbaju merah")

    def test_unknown_customer_rejected(self):
        self.submit(customer=9999)
        self.assertEqual(Order.objects.count(), 0)

    def test_new_customer_is_added_from_separate_modal_not_the_pay_form(self):
        # Pelanggan baru dibuat lewat modal "Pelanggan baru" (form sendiri), bukan isian di form Bayar.
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertNotContains(r, "new_phone")
        self.assertContains(r, "data-qc-open")
        self.assertContains(r, f'action="{reverse("transaction:quick_customer")}"')


class BoardViewTests(TestCase):
    URL = "/staff/admin/manage_transaction/"

    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.courier = User.objects.create_user("cr", password="x", role=Role.COURIER)
        self.budi = Customer.objects.create(
            name="Budi", phone_number="081", address="x"
        )
        self.sari = Customer.objects.create(
            name="Sari", phone_number="082", address="y"
        )
        self.p = make_product("A", stock=50)
        self.client.login(username="adm", password="x")

    def make_order(self, customer=None, method="TUNAI"):
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=self.p, quantity=1)
        return cart.checkout(
            customer=customer or self.budi, admin=self.admin, payment_method=method
        )

    def counts(self, response):
        return {c["css"]: c["count"] for c in response.context["columns"]}

    def test_board_is_default_and_groups_by_status(self):
        a = self.make_order()
        b = self.make_order()
        b.mark_on_delivery(self.courier)
        c = self.make_order()
        c.cancel()
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["view"], "board")
        self.assertEqual(
            self.counts(r),
            {"pending": 0, "confirmed": 1, "on-delivery": 1, "delivered": 0, "cancelled": 1},
        )
        for o in (a, b, c):
            self.assertContains(r, f"Order #{o.pk}")  # modal detail tetap ada
            # kartu bisa diklik dan menunjuk ke modal yang ada di halaman
            self.assertContains(r, f'data-modal="#detailTransaction{o.pk}"')
            self.assertContains(r, f'id="detailTransaction{o.pk}"')

    def test_list_view_still_available(self):
        o = self.make_order()
        r = self.client.get(self.URL, {"view": "list"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["view"], "list")
        self.assertContains(r, f"#{o.pk}")
        self.assertContains(r, "Status Order")

    def test_search_by_customer_name_and_number(self):
        a = self.make_order(self.budi)
        b = self.make_order(self.sari)
        r = self.client.get(self.URL, {"q": "sari"})
        self.assertEqual([o.pk for o in r.context["transactions"]], [b.pk])
        r = self.client.get(self.URL, {"q": f"#{a.pk}"})
        self.assertEqual([o.pk for o in r.context["transactions"]], [a.pk])

    def test_overdue_unpaid_transfer_banner_and_filter(self):
        from datetime import timedelta
        from django.utils import timezone

        late = self.make_order(method="TRANSFER")
        Order.objects.filter(pk=late.pk).update(
            date=timezone.now() - timedelta(hours=2)
        )
        cash = self.make_order(method="TUNAI")
        r = self.client.get(self.URL)
        self.assertEqual(r.context["overdue_unpaid"], 1)  # CASH tidak dihitung
        self.assertContains(r, "belum dibayar lebih dari 1 jam")
        r = self.client.get(self.URL, {"payment": "pending"})
        self.assertTrue(r.context["only_unpaid"])
        pks = {o.pk for o in r.context["transactions"]}
        self.assertEqual(pks, {late.pk, cash.pk})

    def test_closed_columns_are_limited(self):
        from . import views

        for _ in range(views.CLOSED_COLUMN_LIMIT + 2):
            self.make_order().cancel()
        r = self.client.get(self.URL)
        cancelled = [c for c in r.context["columns"] if c["css"] == "cancelled"][0]
        self.assertEqual(len(cancelled["orders"]), views.CLOSED_COLUMN_LIMIT)
        self.assertEqual(cancelled["hidden"], 2)

    def test_non_admin_forbidden(self):
        self.client.logout()
        self.client.login(username="cr", password="x")
        self.assertEqual(self.client.get(self.URL).status_code, 403)


# Akun pelanggan per fitur selalu mendapat pesanan tetap, di luar angka --orders.
FEATURE_USERNAMES = ["demo_belanja", "demo_grooming", "demo_komplain"]


class SeedDemoTests(TestCase):
    def setUp(self):
        # Foto contoh ditulis ke folder sementara, bukan ke media/ milik project.
        import shutil
        import tempfile

        from django.test import override_settings

        media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, media, True)

    def run_seed(self, *args, **kw):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("seed_demo", *args, stdout=out, **kw)
        return out.getvalue()

    def test_refuses_when_debug_is_off(self):
        from django.core.management.base import CommandError
        from django.test import override_settings

        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                self.run_seed()
            self.run_seed(force=True, orders=2)  # --force mengizinkan
        self.assertTrue(Product.objects.exists())

    def test_seed_creates_realistic_data_through_real_rules(self):
        from django.test import override_settings
        from product.models import MutationType
        from transaction.management.commands.seed_demo import CUSTOMERS, FEATURE_CUSTOMERS, PRODUCTS

        with override_settings(DEBUG=True):
            self.run_seed(orders=24)
        self.assertEqual(
            User.objects.filter(username__startswith="demo_", role=Role.ADMIN).count(),
            2,
        )
        self.assertEqual(
            User.objects.filter(username__startswith="demo_", role=Role.COURIER, is_active=True).count(),
            3,
        )
        # + dua calon kurir yang menunggu persetujuan admin (hanya kurir yang bisa daftar sendiri)
        self.assertEqual(
            User.objects.filter(username__startswith="demo_", role=Role.COURIER, approval="MENUNGGU").count(),
            2,
        )
        self.assertFalse(
            User.objects.filter(username__startswith="demo_", approval="MENUNGGU").exclude(role=Role.COURIER).exists()
        )
        self.assertEqual(Customer.objects.count(), len(CUSTOMERS) + 1 + len(FEATURE_CUSTOMERS))  # + akun login
        self.assertEqual(Product.objects.count(), len(PRODUCTS))
        online_and_board = Order.objects.filter(receipt_no__isnull=True).exclude(
            customer__username__in=[row[0] for row in FEATURE_CUSTOMERS]
        )
        self.assertEqual(online_and_board.count(), 24)
        # Transaksi kasir (ber-struk) dibuat terpisah dengan shift, void, retur, dan parkir.
        counter = Order.objects.filter(receipt_no__isnull=False)
        self.assertGreater(counter.count(), 10)
        self.assertTrue(counter.filter(voided_at__isnull=False).exists())
        self.assertTrue(counter.filter(payment_method="CAMPURAN").exists())
        for o in counter:
            self.assertEqual(
                o.total_payment, o.subtotal_before_discount - o.discount + o.tax_amount + o.shipping_fee, o.receipt_no
            )
            self.assertEqual(sum(p.amount for p in o.payments.all()), o.total_payment, o.receipt_no)
        from transaction.models import CashierShift, HeldSale, ReturnRequest

        self.assertEqual(CashierShift.objects.filter(status="BUKA").count(), 1)
        self.assertTrue(CashierShift.objects.filter(difference__lt=0).exclude(close_note="").exists())
        self.assertEqual(set(ReturnRequest.objects.values_list("status", flat=True)), {"MENUNGGU", "DISETUJUI"})
        self.assertEqual(HeldSale.objects.count(), 1)
        self.assertFalse(Product.objects.filter(sku__isnull=True).exists())
        statuses = set(Order.objects.values_list("order_status", flat=True))
        self.assertGreaterEqual(len(statuses), 3)  # campuran status
        # variasi produk untuk menguji halaman stok
        self.assertTrue(Product.objects.filter(stock=0).exists())
        self.assertTrue(Product.objects.filter(selling_price__isnull=True).exists())
        self.assertTrue(Product.objects.filter(is_active=False).exists())
        self.assertTrue(Product.objects.exclude(photo="").exists())
        # stok selalu sama dengan jumlah riwayat mutasi (tidak ada angka yang dikarang)
        for p in Product.objects.all():
            masuk = sum(
                m.quantity for m in p.mutations.filter(mutationType=MutationType.IN)
            )
            keluar = sum(
                m.quantity for m in p.mutations.filter(mutationType=MutationType.OUT)
            )
            self.assertEqual(p.stock, masuk - keluar, p.name)
        # total tiap order = jumlah detailnya; kurir wajib ada untuk order yang sedang diantar
        for o in online_and_board:
            self.assertEqual(o.total_payment, sum(d.subtotal for d in o.details.all()) + o.shipping_fee)
            if o.order_status in ("DALAM_PENGIRIMAN", "TERKIRIM"):
                self.assertIsNotNone(o.courier)

    def test_seed_can_login_and_pages_render(self):
        from django.test import override_settings

        with override_settings(DEBUG=True):
            self.run_seed(orders=10, password="rahasia-123")
        self.assertTrue(
            self.client.login(username="demo_admin", password="rahasia-123")
        )
        for url in (
            "/staff/admin/manage_transaction/",
            "/list",
            "/staff/admin/manage_account",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_seed_is_idempotent_and_more_orders_adds(self):
        from django.test import override_settings

        with override_settings(DEBUG=True):
            self.run_seed(orders=8)
            counts = (
                User.objects.count(),
                Product.objects.count(),
                Customer.objects.count(),
                Order.objects.count(),
            )
            self.run_seed(orders=8)
            self.assertEqual(
                counts,
                (
                    User.objects.count(),
                    Product.objects.count(),
                    Customer.objects.count(),
                    Order.objects.count(),
                ),
            )
            self.run_seed(orders=5, more_orders=True)
            self.assertEqual(Order.objects.filter(receipt_no__isnull=True).exclude(customer__username__in=FEATURE_USERNAMES).count(), 13)

    def test_reset_removes_only_demo_data(self):
        from django.test import override_settings

        from transaction.management.commands.seed_demo import PRODUCTS

        mine = make_product("Produk Milikku", stock=3)
        owner = User.objects.create_user("owner", password="x", role=Role.ADMIN)
        with override_settings(DEBUG=True):
            self.run_seed(orders=10)
            self.run_seed(orders=6, reset=True)
        # order lama dihapus, 6 baru dibuat (+ transaksi kasir demo yang dibuat ulang)
        self.assertEqual(Order.objects.filter(receipt_no__isnull=True).exclude(customer__username__in=FEATURE_USERNAMES).count(), 6)
        self.assertTrue(Product.objects.filter(pk=mine.pk).exists())
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        self.assertEqual(Product.objects.count(), len(PRODUCTS) + 1)


class AddToCartLimitsTests(TestCase):
    def setUp(self):
        from account.models import Role, User
        from product.models import Category, Product

        self.admin = User.objects.create_user("adm2", password="x", role=Role.ADMIN)
        self.client.force_login(self.admin)
        cat, _ = Category.objects.get_or_create(name=Category.FOOD)
        self.product = Product.objects.create(
            category=cat, name="Limited", purchase_price=1, selling_price=2, stock=2
        )

    def add(self, product):
        return self.client.post(f"/staff/admin/cart/add/{product.pk}/")

    def test_cannot_add_more_than_stock(self):
        from transaction.models import CartItem

        for _ in range(4):
            self.add(self.product)
        self.assertEqual(CartItem.objects.get(product=self.product).quantity, 2)

    def test_unsellable_product_is_not_addable(self):
        from product.models import Product
        from transaction.models import CartItem

        hidden = Product.objects.create(
            category=self.product.category, name="No price", purchase_price=1, stock=3
        )
        self.assertEqual(self.add(hidden).status_code, 404)
        self.assertFalse(CartItem.objects.filter(product=hidden).exists())


class PaymentRegistryTests(SimpleTestCase):
    def test_every_method_has_a_handler(self):
        self.assertEqual(set(PAYMENT_REGISTRY), {code for code, _ in PaymentMethod.choices})

    def test_cash_and_transfer_behaviour(self):
        self.assertTrue(PAYMENT_REGISTRY["TUNAI"].paid_after_accepted())
        self.assertFalse(PAYMENT_REGISTRY["TUNAI"].can_be_late())
        self.assertFalse(PAYMENT_REGISTRY["TRANSFER"].paid_after_accepted())
        self.assertTrue(PAYMENT_REGISTRY["TRANSFER"].can_be_late())


class TrackingNumberTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm_t", password="x", role=Role.ADMIN)
        self.customer = Customer.objects.create(
            name="Budi", phone_number="0899", address="x"
        )

    def make_order(self):
        return Order.objects.create(
            admin=self.admin, customer=self.customer, payment_method="TUNAI"
        )

    def test_resi_is_generated_with_expected_format(self):
        import re

        order = self.make_order()
        self.assertRegex(order.tracking_number, r"^PS-\d{6}-[A-HJKMNP-Z2-9]{6}$")

    def test_resi_is_unique_per_order(self):
        resis = {self.make_order().tracking_number for _ in range(20)}
        self.assertEqual(len(resis), 20)

    def test_resi_does_not_change_on_resave(self):
        order = self.make_order()
        first = order.tracking_number
        order.total_payment = 5000
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.tracking_number, first)

    def test_checkout_order_gets_resi(self):
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=make_product("R", 3), quantity=1)
        order = cart.checkout(
            customer=self.customer, admin=self.admin, payment_method="TUNAI"
        )
        self.assertTrue(order.tracking_number)

    def test_normalize_accepts_loose_input(self):
        from transaction.models import normalize_tracking_number

        self.assertEqual(
            normalize_tracking_number(" ps 261022 k7m2qx "), "PS-261022-K7M2QX"
        )
        self.assertEqual(
            normalize_tracking_number("PS261022K7M2QX"), "PS-261022-K7M2QX"
        )
        self.assertEqual(normalize_tracking_number("PS-1"), "")
        self.assertEqual(normalize_tracking_number(""), "")

    def test_timestamps_follow_the_status(self):
        courier = User.objects.create_user("cr_t", password="x", role=Role.COURIER)
        order = self.make_order()
        self.assertIsNone(order.shipped_at)
        order.mark_on_delivery(courier)
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNone(order.delivered_at)
        order.mark_delivered()
        self.assertIsNotNone(order.delivered_at)
        self.assertFalse(order.has_delivery_proof)  # admin boleh tutup tanpa foto



class OnlineOrderTests(TestCase):
    """Customer login memesan langsung; tamu tetap lewat WhatsApp."""

    def setUp(self):
        from account.models import Customer

        self.customer = Customer.objects.create(
            name="Siti Aminah", phone_number="081300000001", address="Jl. Mawar 1"
        )
        self.customer.set_password("rahasia-123")
        self.customer.save()
        self.admin = User.objects.create_user("adm_online", password="x", role=Role.ADMIN)
        self.p1 = make_product("Whiskas", stock=10)
        self.p2 = make_product("Pasir", stock=2)

    def login(self):
        self.client.login(username=self.customer.username, password="rahasia-123")

    def place(self, items, **extra):
        import json

        # Titik peta = lokasi toko bawaan (jarak 0 km -> ongkir dasar Rp 5.000).
        body = {
            "items": items, "payment_method": "TUNAI", "address": "Jl. Melati 7",
            "latitude": "-1.265400", "longitude": "116.831200", **extra,
        }
        return self.client.post(
            "/checkout/pesan/", data=json.dumps(body), content_type="application/json"
        )

    def test_guest_sees_whatsapp_checkout_and_member_sees_system_checkout(self):
        r = self.client.get("/checkout")
        self.assertTemplateUsed(r, "customer/checkout.html")
        self.assertContains(r, "Pesan via WhatsApp")
        self.assertContains(r, "/login?next=/checkout")
        self.login()
        r = self.client.get("/checkout")
        self.assertTemplateUsed(r, "customer/checkout_member.html")
        self.assertNotContains(r, "Pesan via WhatsApp")
        # Koordinat ditulis dengan titik desimal (bukan format lokal "-1,265400") agar terbaca JS.
        self.assertContains(r, 'data-default-lat="-1.265400"')

    def test_place_order_requires_map_pin(self):
        self.login()
        r = self.place([{"id": self.p1.pk, "quantity": 1}], latitude="", longitude="")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["field"], "location")
        self.assertFalse(Order.objects.exists())

    def test_place_order_rejects_pin_outside_delivery_area(self):
        self.login()
        # Samarinda, ±90 km dari toko (maks. 25 km)
        r = self.place([{"id": self.p1.pk, "quantity": 1}], latitude="-0.502200", longitude="117.153600")
        self.assertEqual(r.status_code, 400)
        self.assertIn("di luar jangkauan", r.json()["message"])
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 10)

    def test_shipping_quote(self):
        r = self.client.get("/checkout/ongkir/?latitude=-1.265400&longitude=116.871200")  # ±4,4 km
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["fee"], 5000 + 2 * 2000)
        self.assertEqual(self.client.get("/checkout/ongkir/").status_code, 400)

    def test_staff_gets_guest_checkout(self):
        self.client.login(username="adm_online", password="x")
        self.assertTemplateUsed(self.client.get("/checkout"), "customer/checkout.html")

    def test_place_order_uses_server_prices_and_reduces_stock(self):
        self.login()
        r = self.place([{"id": self.p1.pk, "quantity": 3, "price": 1}, {"id": self.p2.pk, "quantity": 1}])
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        order = Order.objects.get(pk=data["order_id"])
        self.assertEqual(order.order_status, "MENUNGGU")
        self.assertEqual(order.channel, "ONLINE")
        self.assertIsNone(order.admin)
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.shipping_fee, 5000)
        self.assertEqual(order.items_total, 3 * self.p1.selling_price + self.p2.selling_price)
        self.assertEqual(order.total_payment, order.items_total + 5000)
        self.assertTrue(order.has_pin)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 7)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.address, "Jl. Melati 7")
        self.assertIn(f"baru={order.pk}", data["redirect"])

    def test_insufficient_stock_creates_nothing(self):
        self.login()
        r = self.place([{"id": self.p1.pk, "quantity": 1}, {"id": self.p2.pk, "quantity": 5}])
        self.assertEqual(r.status_code, 400)
        self.assertIn("Pasir", r.json()["message"])
        self.assertFalse(Order.objects.exists())
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 10)

    def test_validation_errors(self):
        self.login()
        self.assertEqual(self.place([]).status_code, 400)
        self.assertEqual(self.place([{"id": self.p1.pk, "quantity": 1}], address="").status_code, 400)
        self.assertEqual(
            self.place([{"id": self.p1.pk, "quantity": 1}], payment_method="BITCOIN").status_code, 400
        )
        self.assertEqual(self.place([{"id": 99999, "quantity": 1}]).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_guest_cannot_post_orders(self):
        r = self.place([{"id": self.p1.pk, "quantity": 1}])
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Order.objects.exists())

    def test_my_orders_and_customer_cancel_only_while_waiting(self):
        self.login()
        order = Order.objects.get(pk=self.place([{"id": self.p1.pk, "quantity": 2}]).json()["order_id"])
        r = self.client.get(f"/pesanan-saya/?baru={order.pk}")
        self.assertContains(r, f"Pesanan #{order.pk} berhasil dibuat")
        self.assertContains(r, order.tracking_number)
        self.client.post(f"/pesanan-saya/{order.pk}/batal/")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "DIBATALKAN")
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 10)  # stok kembali

        other = Order.objects.get(pk=self.place([{"id": self.p1.pk, "quantity": 1}]).json()["order_id"])
        other.confirm(self.admin)
        self.client.post(f"/pesanan-saya/{other.pk}/batal/")
        other.refresh_from_db()
        self.assertEqual(other.order_status, "DIKONFIRMASI")

    def test_admin_confirms_from_board(self):
        self.login()
        order_id = self.place([{"id": self.p1.pk, "quantity": 1}]).json()["order_id"]
        self.client.login(username="adm_online", password="x")
        r = self.client.get("/staff/admin/manage_transaction/")
        counts = {c["css"]: c["count"] for c in r.context["columns"]}
        self.assertEqual(counts["pending"], 1)
        self.assertTrue(next(c for c in r.context["columns"] if c["css"] == "pending")["active"])
        self.assertEqual(r.context["pending_online_orders"], 1)
        self.client.post(f"/staff/admin/transaction/{order_id}/status/", {"action": "confirm"})
        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.order_status, "DIKONFIRMASI")
        self.assertEqual(order.admin.username, "adm_online")
        self.assertIsNotNone(order.confirmed_at)
        steps = self.client.get(f"/lacak/{order.tracking_number}/").context["steps"]
        self.assertEqual(
            [s["title"] for s in steps],
            ["Pesanan dibuat", "Dikonfirmasi toko", "Sedang dikirim kurir", "Pesanan sampai"],
        )
