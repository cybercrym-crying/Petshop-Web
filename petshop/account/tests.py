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
