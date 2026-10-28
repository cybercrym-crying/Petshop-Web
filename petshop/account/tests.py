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
        self.edit(other, Role.CASHIER)
        other.refresh_from_db()
        self.assertEqual(other.role, Role.CASHIER)

    def test_admin_cannot_make_admin_accounts(self):
        """Admin punya semua hak kecuali membuat/menaikkan akun menjadi Admin."""
        other = User.objects.create_user("o", password="x", role=Role.COURIER, phone_number="08")
        self.edit(other, Role.ADMIN)
        other.refresh_from_db()
        self.assertEqual(other.role, Role.COURIER)

    def test_superadmin_can_make_admin_accounts(self):
        User.objects.create_user("sup", password="x", role=Role.SUPERADMIN, phone_number="08")
        self.client.login(username="sup", password="x")
        other = User.objects.create_user("o", password="x", role=Role.COURIER, phone_number="08")
        self.edit(other, Role.ADMIN)
        other.refresh_from_db()
        self.assertEqual(other.role, Role.ADMIN)

    def test_admin_cannot_edit_other_admin(self):
        boss = User.objects.create_user("boss2", password="x", role=Role.ADMIN, phone_number="08")
        r = self.edit(boss, Role.COURIER)
        boss.refresh_from_db()
        self.assertEqual(boss.role, Role.ADMIN)
        self.assertIn(r.status_code, (302, 403))

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

    def test_add_customer_with_map_pin_and_detail_address(self):
        from decimal import Decimal
        from .models import Customer
        page = self.client.get("/staff/admin/manage_account?tab=customer")
        self.assertContains(page, "data-map-picker")
        self.assertContains(page, 'name="latitude"')
        self.client.post("/staff/admin/customer/add/", {
            "name": "Sari", "phone_number": "081234567890", "address": "Jl. Mawar 3, pagar hijau",
            "latitude": "-0.502106", "longitude": "117.153709",
        })
        c = Customer.objects.get()
        self.assertEqual((c.latitude, c.longitude), (Decimal("-0.502106"), Decimal("117.153709")))
        self.assertIn("-0.502106,117.153709", c.maps_url)
        # Tanpa titik tetap boleh; titik setengah (hanya lat) ditolak.
        self.client.post(f"/staff/admin/customer/{c.pk}/edit/", {
            "name": "Sari", "phone_number": "081234567890", "address": "Jl. Mawar 3", "latitude": "-0.5",
        })
        c.refresh_from_db()
        self.assertEqual(c.latitude, Decimal("-0.502106"))
        self.client.post(f"/staff/admin/customer/{c.pk}/edit/", {
            "name": "Sari", "phone_number": "081234567890", "address": "Jl. Mawar 3", "latitude": "", "longitude": "",
        })
        c.refresh_from_db()
        self.assertFalse(c.has_pin)

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
        Order.objects.create(admin=admin, customer=c, payment_method="TUNAI")
        r = self.client.post(f"/staff/admin/customer/{c.pk}/delete/", follow=True)
        self.assertTrue(Customer.objects.filter(pk=c.pk).exists())
        self.assertContains(r, "riwayat pesanan")


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

    def order(self, courier=None, status="DIKONFIRMASI"):
        from transaction.models import Order

        return Order.objects.create(
            admin=self.admin, courier=courier, customer=self.customer,
            payment_method="TUNAI", total_payment=50000, order_status=status,
        )

    def test_courier_profile_shows_stats_and_orders(self):
        self.order(self.courier, "DALAM_PENGIRIMAN")
        self.order(self.courier, "TERKIRIM")
        self.order(self.courier, "TERKIRIM")
        r = self.client.get(f"/staff/admin/employee/{self.courier.pk}/")
        self.assertEqual(r.status_code, 200)
        by = {s["label"]: s["value"] for s in r.context["stats"]}
        self.assertEqual(by, {"Ditugaskan": 3, "Dalam pengiriman": 1, "Terkirim": 2})
        self.assertEqual(len(r.context["recent_orders"]), 3)
        self.assertContains(r, "Budi Santoso")
        self.assertContains(r, "https://wa.me/6281234567890")
        self.assertContains(r, "Rp 50.000")

    def test_admin_profile_counts_orders_created(self):
        self.order(None, "DIKONFIRMASI")
        self.order(None, "TERKIRIM")
        r = self.client.get(f"/staff/admin/employee/{self.admin.pk}/")
        by = {s["label"]: s["value"] for s in r.context["stats"]}
        self.assertEqual(by, {"Order dibuat": 2, "Masih berjalan": 1, "Terkirim": 1})
        self.assertTrue(r.context["is_self"])
        self.assertNotContains(r, "Delete employee")  # tidak bisa hapus diri sendiri
        self.assertContains(r, "Anda tidak bisa mengubah peran Anda sendiri.")

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
            "phone_number": "0812", "role": "KURIR", **extra,
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
        self.order(self.courier, "TERKIRIM")
        profile = f"/staff/admin/employee/{self.courier.pk}/"
        r = self.client.post(f"/staff/admin/employee/{self.courier.pk}/delete/", {"next": profile})
        self.assertRedirects(r, profile, fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(pk=self.courier.pk).exists())
        self.assertIn("riwayat pesanan", [str(m) for m in get_messages(r.wsgi_request)][0])

    def test_delete_employee_without_orders_works(self):
        r = self.client.post(f"/staff/admin/employee/{self.courier.pk}/delete/")
        self.assertRedirects(r, "/staff/admin/manage_account", fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.courier.pk).exists())

    def test_manage_account_links_to_profile_with_activity(self):
        self.order(self.courier, "TERKIRIM")
        self.order(None, "DIKONFIRMASI")
        r = self.client.get("/staff/admin/manage_account")
        self.assertContains(r, f"/staff/admin/employee/{self.courier.pk}/")
        self.assertContains(r, "1 terkirim")
        self.assertContains(r, "2 order")
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
            self.assertContains(r, "staff_sidebar.css", msg_prefix=url)
            self.assertContains(r, 'id="staffSidebar"', msg_prefix=url)

    def test_login_page_uses_existing_bootstrap_and_orange_variable(self):
        from django.contrib.staticfiles import finders

        self.client.logout()
        r = self.client.get("/login")
        self.assertContains(r, "vendor/bootstrap/css/bootstrap.min.css")
        self.assertNotContains(r, "styles/bootstrap.min.css")
        self.assertTrue(finders.find("vendor/bootstrap/css/bootstrap.min.css"))
        # CSS login kini ada di file static (bukan <style> di HTML).
        self.assertContains(r, "account/css/login.css")
        with open(finders.find("account/css/login.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertNotIn("--Employee", css)
        self.assertIn("--orange: #f0a63c", css)

    def test_account_tables_collapse_to_cards_on_phone(self):
        r = self.client.get("/staff/admin/manage_account")
        self.assertContains(r, 'emp-table"')
        self.assertContains(r, 'cust-table"')
        self.assertContains(r, 'data-label="No. HP"')
        self.assertContains(r, 'class="tbl-head"')

    def test_all_static_references_in_live_templates_exist(self):
        import glob
        import re

        from django.contrib.staticfiles import finders

        missing = []
        # template tiap app (<app>/templates/) dan template bersama (templates/)
        paths = glob.glob("*/templates/**/*.html", recursive=True)
        paths += glob.glob("templates/**/*.html", recursive=True)
        for path in paths:
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
        self.assertEqual(self.client.get("/staff/admin/manage_account").status_code, 200)


    def test_dashboard_shows_store_summary(self):
        self.client.login(username="boss", password="Pass12345!x")
        r = self.client.get("/staff/admin/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "account/admin_dashboard.html")
        self.assertContains(r, "Ringkasan Toko")
        self.assertContains(r, "Penjualan lunas")

    def test_admin_pages_render_sidebar(self):
        self.client.login(username="boss", password="Pass12345!x")
        r = self.client.get("/staff/admin/manage_account")
        self.assertContains(r, 'id="staffSidebar"')

    def test_admin_pages_have_dark_mode_toggle(self):
        self.client.login(username="boss", password="Pass12345!x")
        for url in ("/staff/admin/manage_account", "/staff/admin/make_transaction/", "/list"):
            r = self.client.get(url)
            self.assertContains(r, "data-staff-theme-toggle", msg_prefix=url)
            self.assertContains(r, "staff_theme.css", msg_prefix=url)

    def test_dark_theme_vars_are_defined_for_admin_css(self):
        """Tiap variabel --t-* yang dipakai CSS admin harus punya cadangan terang; nilai gelap ada di staff_theme.css."""
        import glob
        import re

        theme = open("account/static/account/css/staff_theme.css", encoding="utf-8").read()
        defined = set(re.findall(r"(--t-[a-z]+-[0-9a-f]+):", theme))
        self.assertTrue(defined)
        used = set()
        for path in glob.glob("*/static/*/css/*.css"):
            used |= set(re.findall(r"var\((--t-[a-z]+-[0-9a-f]+),#[0-9a-fA-F]+\)", open(path, encoding="utf-8").read()))
        self.assertTrue(defined <= used, sorted(defined - used))


class StaticStructureTests(TestCase):
    """Penjaga struktur: CSS/JS tidak boleh kembali ke dalam HTML, dan static tiap app diberi namespace."""

    def live_templates(self):
        import glob

        paths = glob.glob("*/templates/**/*.html", recursive=True)
        paths += glob.glob("templates/**/*.html", recursive=True)
        return [p for p in paths if not p.startswith("_unused")]

    def test_no_inline_style_or_script_blocks_in_templates(self):
        import re

        found = []
        for path in self.live_templates():
            text = open(path, encoding="utf-8").read()
            for m in re.finditer(r"<(style|script)\b([^>]*)>(.*?)</\1>", text, re.S):
                if m.group(1) == "script" and "src=" in m.group(2):
                    continue
                if m.group(3).strip():
                    found.append((path, m.group(1)))
        self.assertEqual(found, [], "pindahkan kode ke file di <app>/static/<app>/")

    def test_no_inline_event_handler_attributes(self):
        import re

        found = []
        for path in self.live_templates():
            text = open(path, encoding="utf-8").read()
            found += [(path, m) for m in re.findall(r"\son(?:click|submit|change)=", text)]
        self.assertEqual(found, [], "pakai data-confirm / data-href / data-autosubmit (static/js/common.js)")

    def test_app_static_files_are_namespaced(self):
        import glob
        import os

        bad = []
        for path in glob.glob("*/static/**/*", recursive=True):
            if not os.path.isfile(path):
                continue
            app, _, rest = path.partition("/static/")
            if not rest.startswith(app + "/"):
                bad.append(path)
        self.assertEqual(bad, [], "file static app harus di <app>/static/<app>/...")

    def test_shared_static_and_templates_live_at_project_level(self):
        from django.contrib.staticfiles import finders
        from django.template.loader import get_template

        for name in ("vendor/bootstrap/css/bootstrap.min.css", "js/common.js", "account/css/staff_sidebar.css", "account/js/staff_sidebar.js", "css/base.css"):
            self.assertTrue(finders.find(name), name)
        for name in ("base.html", "403.html", "partials/navbar.html", "partials/staff_nav.html"):
            get_template(name)



class RoleBehaviorTests(TestCase):
    def test_each_role_has_its_own_behavior(self):
        from account.models import AdminRole, CourierRole, CustomerRole

        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        kurir = User.objects.create_user("kur", password="x", role=Role.COURIER)
        biasa = User.objects.create_user("biasa", password="x", role="")
        self.assertIsInstance(admin.role_behavior, AdminRole)
        self.assertIsInstance(kurir.role_behavior, CourierRole)
        self.assertIsInstance(biasa.role_behavior, CustomerRole)
        self.assertTrue(admin.role_behavior.can_access_admin())
        self.assertFalse(kurir.role_behavior.can_access_admin())
        self.assertFalse(biasa.role_behavior.can_access_admin())
        self.assertEqual(admin.dashboard_url_name, "staff_admin_dashboard")
        self.assertEqual(kurir.dashboard_url_name, "courier:dashboard")
        self.assertEqual(biasa.dashboard_url_name, "customer:dashboard")

    def test_abstract_role_cannot_be_instantiated(self):
        from account.models import RoleBehavior

        with self.assertRaises(TypeError):
            RoleBehavior()

    def test_business_exceptions_share_one_parent(self):
        from common.exceptions import PetshopError
        from product.models import InsufficientStock
        from transaction.models import CheckoutError, InvalidTransition

        for kelas in (InsufficientStock, CheckoutError, InvalidTransition):
            self.assertTrue(issubclass(kelas, PetshopError))
