"""Tes untuk dasbor admin, laporan CSV, halaman akun pelanggan, dan batas login."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account import dashboard
from account.models import Customer, Role, User
from product.models import Category, Product
from transaction.models import Order, OrderDetail, OrderStatus, PaymentStatus


def make_order(customer, total, *, paid, status=OrderStatus.CONFIRMED, days_ago=0, product=None):
    order = Order.objects.create(
        customer=customer,
        payment_method="TUNAI",
        payment_status=PaymentStatus.PAID if paid else PaymentStatus.PENDING,
        order_status=status,
        total_payment=total,
        date=timezone.now() - timedelta(days=days_ago),
    )
    if product is not None:
        OrderDetail.objects.create(
            transaction=order, product=product, quantity=2, unit_price=total // 2, subtotal=total
        )
    return order


class DashboardMetricTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", role=Role.ADMIN)
        self.customer = Customer.objects.create(name="Siti", phone_number="0811", address="x")
        category = Category.objects.create(name=Category.FOOD)
        self.product = Product.objects.create(
            category=category, name="Whiskas", purchase_price=1000, selling_price=2000, stock=3
        )

    def test_sales_only_count_paid_and_not_cancelled_orders(self):
        make_order(self.customer, 50000, paid=True, product=self.product)
        make_order(self.customer, 7000, paid=False)
        make_order(self.customer, 9000, paid=True, status=OrderStatus.CANCELLED)
        make_order(self.customer, 11000, paid=True, days_ago=40)  # di luar 30 hari
        data = dashboard.summary(dashboard.Period.last_days(30))
        self.assertEqual(data["sales"]["total"], 50000)
        self.assertEqual(data["sales"]["n"], 1)
        self.assertEqual(data["orders"]["n"], 2)  # lunas + belum lunas, tanpa yang batal
        self.assertEqual(data["work"]["unpaid_total"], 7000)
        self.assertEqual(data["stock"]["low"], 1)

    def test_trend_has_one_point_per_day(self):
        make_order(self.customer, 50000, paid=True)
        trend = dashboard.sales_trend(dashboard.Period.last_days(7))
        self.assertEqual(len(trend), 7)
        self.assertEqual(trend[-1]["total"], 50000)
        self.assertEqual(trend[-1]["pct"], 100)

    def test_top_products_excludes_cancelled(self):
        make_order(self.customer, 4000, paid=True, product=self.product)
        make_order(self.customer, 4000, paid=True, status=OrderStatus.CANCELLED, product=self.product)
        top = dashboard.top_products(dashboard.Period.last_days(30))
        self.assertEqual(top[0]["qty"], 2)

    def test_dashboard_shows_action_tiles_and_courier_status(self):
        busy = User.objects.create_user("kurir_a", password="x", role=Role.COURIER, first_name="Ani")
        User.objects.create_user("kurir_b", password="x", role=Role.COURIER, first_name="Bayu")
        order = make_order(self.customer, 7000, paid=False, status=OrderStatus.ON_DELIVERY)
        Order.objects.filter(pk=order.pk).update(courier=busy)
        rows = {r["user"].username: r for r in dashboard.couriers_now()}
        self.assertEqual(rows["kurir_a"]["tone"], "warn")
        self.assertEqual(rows["kurir_b"]["tone"], "ok")
        self.client.login(username="boss", password="x")
        r = self.client.get(reverse("staff_admin_dashboard"))
        self.assertContains(r, "Perlu tindakan sekarang")
        self.assertContains(r, 'class="ad-task-list"')
        self.assertContains(r, "1 paket di jalan")
        self.assertContains(r, "Tidak membawa paket")

    def test_tasks_grouped_in_fixed_order(self):
        tasks = [
            {"group": "stock", "label": "habis"},
            {"group": "pay", "label": "bukti"},
            {"group": "order", "label": "kemas"},
            {"group": "pay", "label": "cod"},
        ]
        groups = dashboard.group_tasks(tasks)
        self.assertEqual([g["key"] for g in groups], ["pay", "order", "stock"])
        self.assertEqual([t["label"] for t in groups[0]["items"]], ["bukti", "cod"])

    def test_dashboard_page_and_csv_for_admin_only(self):
        make_order(self.customer, 50000, paid=True)
        self.client.force_login(self.admin)
        r = self.client.get(reverse("staff_admin_dashboard"), {"range": "7"})
        self.assertContains(r, "Rp 50.000")
        self.assertContains(r, 'id="ad-trend-data"')  # data grafik garis
        csv = self.client.get(reverse("sales_report_csv"), {"range": "7"})
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("50000", csv.content.decode("utf-8"))
        kasir = User.objects.create_user("ksr", password="x", role=Role.CASHIER)
        self.client.force_login(kasir)
        self.assertEqual(self.client.get(reverse("staff_admin_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sales_report_csv")).status_code, 403)

    def test_csv_neutralises_formula_names(self):
        evil = Customer.objects.create(name="=HYPERLINK(1)", phone_number="0812", address="x")
        make_order(evil, 1000, paid=True)
        self.client.force_login(self.admin)
        body = self.client.get(reverse("sales_report_csv")).content.decode("utf-8")
        self.assertIn("'=HYPERLINK(1)", body)

    def test_unknown_range_falls_back_to_default(self):
        self.assertEqual(dashboard.parse_range("999"), dashboard.DEFAULT_RANGE)
        self.assertEqual(dashboard.parse_range("7"), 7)


class CustomerAccountPageTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Siti Aminah", phone_number="081300000001", address="Jl. Mawar"
        )
        self.customer.set_password("rahasia-lama-1")
        self.customer.save()
        self.client.login(username=self.customer.username, password="rahasia-lama-1")

    def test_update_profile(self):
        r = self.client.post(
            reverse("customer:account"),
            {
                "form": "profile",
                "name": "Siti Rahma",
                "phone_number": "+62 813-0000-0002",
                "email": "",
                "address": "Jl. Melati 2",
            },
        )
        self.assertRedirects(r, reverse("customer:account"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Siti Rahma")
        self.assertEqual(self.customer.phone_number, "081300000002")
        self.assertEqual(self.customer.address, "Jl. Melati 2")

    def test_phone_used_by_other_customer_is_rejected(self):
        Customer.objects.create(name="Lain", phone_number="081300000009", address="x")
        r = self.client.post(
            reverse("customer:account"),
            {"form": "profile", "name": "Siti", "phone_number": "081300000009", "address": "x"},
        )
        self.assertContains(r, "sudah dipakai pelanggan lain")

    def test_change_password_keeps_session(self):
        r = self.client.post(
            reverse("customer:account"),
            {
                "form": "password",
                "old_password": "rahasia-lama-1",
                "new_password1": "Sandi-Baru-2026",
                "new_password2": "Sandi-Baru-2026",
            },
        )
        self.assertRedirects(r, reverse("customer:account"))
        self.assertEqual(self.client.get(reverse("customer:account")).status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("Sandi-Baru-2026"))

    def test_staff_cannot_open_customer_account_page(self):
        staff = User.objects.create_user("kurir", password="x", role=Role.COURIER)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("customer:account")).status_code, 403)


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("boss", password="Benar-12345", role=Role.ADMIN)

    def tearDown(self):
        cache.clear()

    def test_locks_after_repeated_failures(self):
        for _ in range(5):
            r = self.client.post("/login", {"username": "boss", "password": "salah"})
            self.assertContains(r, "kata sandi salah")
        r = self.client.post("/login", {"username": "boss", "password": "Benar-12345"})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_resets_counter(self):
        for _ in range(4):
            self.client.post("/login", {"username": "boss", "password": "salah"})
        r = self.client.post("/login", {"username": "boss", "password": "Benar-12345"})
        self.assertEqual(r.status_code, 302)


class ErrorPageTests(TestCase):
    def test_404_uses_friendly_template(self):
        r = self.client.get("/tidak-ada-halaman-ini/")
        self.assertEqual(r.status_code, 404)
        self.assertTemplateUsed(r, "404.html")
        self.assertContains(r, "Halaman tidak ditemukan", status_code=404)
