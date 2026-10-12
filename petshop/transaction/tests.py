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
        self.courier = User.objects.create_user("cr", password="x", role=Role.COURIR)
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
        self.assertIsNone(self.checkout().courir)

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
        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        customer = Customer.objects.create(name="Budi", phone_number="08", address="x")
        self.p = make_product("A", stock=5)
        cart = Cart.objects.create(user=admin)
        CartItem.objects.create(cart=cart, product=self.p, quantity=2)
        self.order = cart.checkout(
            customer=customer, admin=admin, payment_method="CASH"
        )

    def test_happy_path(self):
        self.order.mark_on_delivery()
        self.order.mark_success()
        self.assertEqual(self.order.order_status, OrderStatus.SUCCESS)
        self.assertEqual(self.order.payment_status, PaymentStatus.SUCCESS)

    def test_failed_restores_stock(self):
        self.order.mark_failed()
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)
        self.assertEqual(self.order.payment_status, PaymentStatus.FAILED)

    def test_illegal_transition(self):
        self.order.mark_success()
        with self.assertRaises(InvalidTransition):
            self.order.mark_on_delivery()
        with self.assertRaises(InvalidTransition):
            self.order.mark_failed()


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.customer = Customer.objects.create(
            name="Budi", phone_number="08", address="x"
        )
        self.p = make_product("A", stock=3)
        self.client.login(username="adm", password="x")

    def test_make_transaction_page_loads(self):
        User.objects.create_user("cr", password="x", role=Role.COURIR)
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
