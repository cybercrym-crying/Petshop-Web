from django.test import TestCase
from account.models import User, Customer, Role
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
            customer=self.customer, admin=self.admin, payment_method="CASH", **kw
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
        self.order = cart.checkout(customer=customer, admin=self.admin, payment_method="CASH")

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
        self.client.post(f"/staff/admin/cart/add/{self.p.pk}/")
        self.client.post(f"/staff/admin/cart/add/{self.p.pk}/")
        self.client.post(
            "/staff/admin/cart/submit/",
            {"customer": self.customer.pk, "payment_method": "CASH", "courier": ""},
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
        self.order = cart.checkout(customer=customer, admin=self.admin, payment_method="CASH")
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

    def test_full_flow(self):
        self.act("on_delivery", courier=self.courier.pk)
        self.act("delivered")
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.DELIVERED)
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)
        self.assertEqual(self.order.courier, self.courier)

    def test_on_delivery_without_courier_rejected(self):
        self.act("on_delivery")
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)

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
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=self.p, quantity=1)

    def submit(self, **data):
        return self.client.post(
            "/staff/admin/cart/submit/", {"payment_method": "CASH", **data}
        )

    def test_selected_customer_used(self):
        c = Customer.objects.create(name="Budi", phone_number="081234567890", address="x")
        self.submit(customer=c.pk)
        self.assertEqual(Order.objects.get().customer, c)

    def test_no_customer_rejected(self):
        self.submit()
        self.assertEqual(Order.objects.count(), 0)

    def test_unknown_customer_rejected(self):
        self.submit(customer=9999)
        self.assertEqual(Order.objects.count(), 0)

    def test_page_has_no_inline_new_customer_fields_but_links_to_manage_account(self):
        r = self.client.get("/staff/admin/make_transaction/")
        self.assertNotContains(r, "new_phone")
        self.assertContains(r, "manage_account?tab=customer")
