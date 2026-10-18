from django.contrib.messages import get_messages
from django.test import TestCase
from .models import User, Role


class EmployeeViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "adm", password="x", role=Role.ADMIN, phone_number="08"
        )
        self.client.login(username="adm", password="x")

    def edit(self, user, role):
        return self.client.post(
            f"/staff/admin/employee/{user.pk}/edit/",
            {
                "username": user.username, "first_name": "A", "last_name": "B",
                "phone_number": "08", "role": role,
            },
        )

    def test_cannot_change_own_role(self):
        self.edit(self.admin, Role.COURIER)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_can_change_other_role(self):
        other = User.objects.create_user("o", password="x", role=Role.COURIER, phone_number="08")
        self.edit(other, Role.ADMIN)
        other.refresh_from_db()
        self.assertEqual(other.role, Role.ADMIN)

    def test_add_employee_error_has_no_html(self):
        r = self.client.post(
            "/staff/admin/employee/add/",
            {"username": "n", "role": Role.COURIER, "phone_number": "08"},  # tanpa password
        )
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(msgs)
        self.assertFalse(any("<" in m for m in msgs))


class PhoneTests(TestCase):
    def test_normalize_formats(self):
        from .phone import normalize_phone
        for raw in ["0812-3456-7890", "+62 812 3456 7890", "6281234567890", "81234567890"]:
            self.assertEqual(normalize_phone(raw), "081234567890")

    def test_invalid(self):
        from .phone import normalize_phone
        for raw in ["", "abc", "123", "0812abc"]:
            with self.assertRaises(ValueError):
                normalize_phone(raw)

    def test_customer_form_normalizes_and_blocks_duplicate(self):
        from .form import CustomerForm
        from .models import Customer
        Customer.objects.create(name="A", phone_number="081234567890", address="x")
        form = CustomerForm({"name": "B", "phone_number": "+62 812-3456-7890", "address": "y"})
        self.assertFalse(form.is_valid())
        self.assertIn("phone_number", form.errors)

    def test_whatsapp_url(self):
        from .models import Customer
        c = Customer(name="A", phone_number="081234567890", address="x")
        self.assertEqual(c.whatsapp_url, "https://wa.me/6281234567890")


class CustomerLinksAndManageTests(TestCase):
    def setUp(self):
        User.objects.create_user("adm", password="x", role=Role.ADMIN, phone_number="08")
        self.client.login(username="adm", password="x")

    def test_maps_url_encodes_address(self):
        from .models import Customer
        c = Customer(name="A", phone_number="081234567890", address="Jl. Merpati No 18, Balikpapan")
        self.assertEqual(
            c.maps_url,
            "https://www.google.com/maps/search/?api=1&query=Jl.%20Merpati%20No%2018%2C%20Balikpapan",
        )

    def test_customer_tab_shows_wa_and_maps_links(self):
        from .models import Customer
        Customer.objects.create(name="Budi", phone_number="081234567890", address="Jl A")
        r = self.client.get("/staff/admin/manage_account?tab=customer")
        self.assertContains(r, "https://wa.me/6281234567890")
        self.assertContains(r, "google.com/maps/search")

    def test_add_customer_normalizes_and_returns_to_customer_tab(self):
        from .models import Customer
        r = self.client.post(
            "/staff/admin/customer/add/",
            {"name": "Sari", "phone_number": "+62 812-3456-7890", "address": "Jl B"},
        )
        self.assertRedirects(r, "/staff/admin/manage_account?tab=customer", fetch_redirect_response=False)
        self.assertEqual(Customer.objects.get().phone_number, "081234567890")

    def test_add_duplicate_customer_shows_error(self):
        from .models import Customer
        Customer.objects.create(name="A", phone_number="081234567890", address="x")
        r = self.client.post(
            "/staff/admin/customer/add/",
            {"name": "B", "phone_number": "6281234567890", "address": "y"},
            follow=True,
        )
        self.assertEqual(Customer.objects.count(), 1)
        self.assertContains(r, "phone_number")

    def test_delete_customer_with_orders_is_blocked_not_crashing(self):
        from .models import Customer
        from transaction.models import Order
        admin = User.objects.get(username="adm")
        c = Customer.objects.create(name="A", phone_number="081234567890", address="x")
        Order.objects.create(admin=admin, customer=c, payment_method="CASH")
        r = self.client.post(f"/staff/admin/customer/{c.pk}/delete/", follow=True)
        self.assertTrue(Customer.objects.filter(pk=c.pk).exists())
        self.assertContains(r, "riwayat order")


class EmployeeProfileTests(TestCase):
    def setUp(self):
        from account.models import Customer

        self.admin = User.objects.create_user(
            "adm", password="x", role=Role.ADMIN, phone_number="0811", first_name="Ani", last_name="Admin"
        )
        self.courier = User.objects.create_user(
            "bud", password="x", role=Role.COURIER, phone_number="0812-3456-7890",
            first_name="Budi", last_name="Santoso",
        )
        self.customer = Customer.objects.create(name="Siti", phone_number="0899", address="x")
        self.client.login(username="adm", password="x")

    def order(self, courier=None, status="CONFIRMED"):
        from transaction.models import Order

        return Order.objects.create(
            admin=self.admin, courier=courier, customer=self.customer,
            payment_method="CASH", total_payment=50000, order_status=status,
        )

    def test_courier_profile_shows_stats_and_orders(self):
        self.order(self.courier, "ON_DELIVERY")
        self.order(self.courier, "DELIVERED")
        self.order(self.courier, "DELIVERED")
        r = self.client.get(f"/staff/admin/employee/{self.courier.pk}/")
        self.assertEqual(r.status_code, 200)
        by = {s["label"]: s["value"] for s in r.context["stats"]}
        self.assertEqual(by, {"Assigned": 3, "On delivery": 1, "Delivered": 2})
        self.assertEqual(len(r.context["recent_orders"]), 3)
        self.assertContains(r, "Budi Santoso")
        self.assertContains(r, "https://wa.me/6281234567890")
        self.assertContains(r, "Rp 50.000")

    def test_admin_profile_counts_orders_created(self):
        self.order(None, "CONFIRMED")
        self.order(None, "DELIVERED")
        r = self.client.get(f"/staff/admin/employee/{self.admin.pk}/")
        by = {s["label"]: s["value"] for s in r.context["stats"]}
        self.assertEqual(by, {"Orders created": 2, "Still open": 1, "Delivered": 1})
        self.assertTrue(r.context["is_self"])
        self.assertNotContains(r, "Delete employee")  # tidak bisa hapus diri sendiri
        self.assertContains(r, "You cannot change your own role.")

    def test_unknown_employee_404_and_courier_forbidden(self):
        self.assertEqual(self.client.get("/staff/admin/employee/9999/").status_code, 404)
        self.client.logout()
        self.client.login(username="bud", password="x")
        self.assertEqual(
            self.client.get(f"/staff/admin/employee/{self.courier.pk}/").status_code, 403
        )

    def post_edit(self, **extra):
        data = {
            "username": "bud", "first_name": "Budi", "last_name": "Baru",
            "phone_number": "0812", "role": "COURIER", **extra,
        }
        return self.client.post(f"/staff/admin/employee/{self.courier.pk}/edit/", data)

    def test_edit_from_profile_returns_to_profile(self):
        profile = f"/staff/admin/employee/{self.courier.pk}/"
        r = self.post_edit(next=profile)
        self.assertRedirects(r, profile, fetch_redirect_response=False)
        self.courier.refresh_from_db()
        self.assertEqual(self.courier.last_name, "Baru")

    def test_unsafe_next_is_ignored(self):
        r = self.post_edit(next="https://evil.example.com/")
        self.assertRedirects(r, "/staff/admin/manage_account", fetch_redirect_response=False)

    def test_delete_employee_with_orders_is_blocked_not_crash(self):
        self.order(self.courier, "DELIVERED")
        profile = f"/staff/admin/employee/{self.courier.pk}/"
        r = self.client.post(f"/staff/admin/employee/{self.courier.pk}/delete/", {"next": profile})
        self.assertRedirects(r, profile, fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(pk=self.courier.pk).exists())
        self.assertIn("riwayat order", [str(m) for m in get_messages(r.wsgi_request)][0])

    def test_delete_employee_without_orders_works(self):
        r = self.client.post(f"/staff/admin/employee/{self.courier.pk}/delete/")
        self.assertRedirects(r, "/staff/admin/manage_account", fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.courier.pk).exists())

    def test_manage_account_links_to_profile_with_activity(self):
        self.order(self.courier, "DELIVERED")
        self.order(None, "CONFIRMED")
        r = self.client.get("/staff/admin/manage_account")
        self.assertContains(r, f"/staff/admin/employee/{self.courier.pk}/")
        self.assertContains(r, "1 delivered")
        self.assertContains(r, "2 orders created")
        self.assertNotContains(r, "*********")


class MobileReadinessTests(TestCase):
    """Perbaikan tampilan HP: header staff, referensi file statis, form login."""

    def setUp(self):
        self.admin = User.objects.create_user(
            "adm", password="x", role=Role.ADMIN, first_name="Ani", last_name="Admin"
        )
        self.client.login(username="adm", password="x")

    def test_staff_pages_have_logout_in_header(self):
        for url in (
            "/staff/admin/manage_transaction/",
            "/staff/admin/make_transaction/",
            "/staff/admin/manage_product/",
            "/staff/admin/manage_account",
            "/list",
            f"/staff/admin/employee/{self.admin.pk}/",
        ):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, 'action="/logout"', msg_prefix=url)
            self.assertContains(r, "staff_nav.css", msg_prefix=url)

    def test_login_page_uses_existing_bootstrap_and_orange_variable(self):
        from django.contrib.staticfiles import finders

        self.client.logout()
        r = self.client.get("/login")
        self.assertContains(r, "css/bootstrap.min.css")
        self.assertNotContains(r, "styles/bootstrap.min.css")
        self.assertNotContains(r, "--Employee")
        self.assertContains(r, "--orange: #f0a63c")
        self.assertTrue(finders.find("css/bootstrap.min.css"))

    def test_account_tables_collapse_to_cards_on_phone(self):
        r = self.client.get("/staff/admin/manage_account")
        self.assertContains(r, 'class="emp-table"')
        self.assertContains(r, 'class="cust-table"')
        self.assertContains(r, 'data-label="Phone"')
        self.assertContains(r, 'class="tbl-head"')

    def test_all_static_references_in_live_templates_exist(self):
        import glob
        import re

        from django.contrib.staticfiles import finders

        missing = []
        for path in glob.glob("*/templates/**/*.html", recursive=True):
            text = open(path, encoding="utf-8").read()
            for m in re.finditer(r"{%\s*static\s+['\"]([^'\"]+)['\"]", text):
                if not finders.find(m.group(1)):
                    missing.append((path, m.group(1)))
        self.assertEqual(missing, [])


class LoginNextAndSelfPasswordTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "boss", password="Pass12345!x", role=Role.ADMIN, phone_number="0811111111"
        )

    def test_login_redirects_to_next_when_safe(self):
        r = self.client.post(
            "/login?next=/staff/admin/manage_product/",
            {"username": "boss", "password": "Pass12345!x"},
        )
        self.assertRedirects(r, "/staff/admin/manage_product/", fetch_redirect_response=False)

    def test_login_ignores_external_next(self):
        r = self.client.post(
            "/login?next=https://evil.example/",
            {"username": "boss", "password": "Pass12345!x"},
        )
        self.assertRedirects(r, "/staff/admin/dashboard", fetch_redirect_response=False)

    def test_changing_own_password_keeps_you_logged_in(self):
        self.client.login(username="boss", password="Pass12345!x")
        r = self.client.post(
            f"/staff/admin/employee/{self.admin.pk}/edit/",
            {
                "username": "boss",
                "first_name": "",
                "last_name": "",
                "phone_number": "0811111111",
                "role": "ADMIN",
                "password": "NewPass98765!y",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("NewPass98765!y"))
        self.assertEqual(self.client.get("/staff/admin/dashboard").status_code, 200)
