from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from account.models import Approval, Role, User

from .models import ActivityLog, BankAccount, Notification, StoreSettings, haversine_km, tiered_fee


def make_user(username, role, **extra):
    phone = "0811" + str(User.objects.count() + 1000000)
    return User.objects.create_user(username, password="Pass12345!x", role=role, phone_number=phone, **extra)


class StoreSettingsModelTests(TestCase):
    def test_singleton(self):
        a = StoreSettings.current()
        b = StoreSettings.current()
        self.assertEqual(a.pk, b.pk)
        StoreSettings(name="Lain").save()
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_shipping_fee_is_tiered(self):
        store = StoreSettings.current()  # 5000 untuk 3 km pertama, +2000/km
        self.assertEqual(store.shipping_fee(2.5), 5000)
        self.assertEqual(store.shipping_fee(3.2), 7000)
        self.assertEqual(store.shipping_fee(7), 13000)
        self.assertEqual(tiered_fee(0, 1000, 0, 500), 1000)

    def test_pickup_fee_counts_both_ways(self):
        store = StoreSettings.current()
        self.assertEqual(store.pickup_fee(2), 20000)
        self.assertEqual(store.pickup_fee(2, trips=1), 10000)

    def test_haversine(self):
        # Balikpapan -> Samarinda ±90 km garis lurus
        km = haversine_km(-1.2654, 116.8312, -0.5022, 117.1536)
        self.assertTrue(80 < km < 100, km)

    def test_whatsapp_display(self):
        store = StoreSettings(whatsapp="6281356703075")
        self.assertEqual(store.whatsapp_display, "0813-5670-3075")


class StoreSettingsPageTests(TestCase):
    def setUp(self):
        self.admin = make_user("adm", Role.ADMIN)

    def post_data(self, **override):
        data = {
            "name": "Seelly Petshop", "address": "Jl. Contoh 1", "latitude": "-1.250000",
            "longitude": "116.850000", "open_hour": 8, "close_hour": 21, "whatsapp": "0812-3456-7890",
            "email": "toko@example.com", "shipping_base_fee": 6000, "shipping_base_km": "2",
            "shipping_per_km": 2500, "max_delivery_km": "20", "pickup_base_fee": 10000,
            "pickup_base_km": "3", "pickup_per_km": 3000, "max_packages_per_courier": 8,
            "payment_deadline_hours": 24, "gps_stale_seconds": 120, "grooming_reminder_days": 30,
            "bank-TOTAL_FORMS": "1", "bank-INITIAL_FORMS": "0", "bank-MIN_NUM_FORMS": "0",
            "bank-MAX_NUM_FORMS": "1000",
            "bank-0-bank": "BCA", "bank-0-number": "1234567890", "bank-0-holder": "Seelly", "bank-0-is_active": "on",
        }
        data.update(override)
        return data

    def test_cashier_and_courier_cannot_open(self):
        for role in (Role.CASHIER, Role.COURIER, Role.CUSTOMER):
            make_user(f"u{role}", role)
            self.client.login(username=f"u{role}", password="Pass12345!x")
            self.assertEqual(self.client.get(reverse("store:settings")).status_code, 403, role)

    def test_admin_and_superadmin_can_save(self):
        make_user("sup", Role.SUPERADMIN)
        for username in ("adm", "sup"):
            self.client.login(username=username, password="Pass12345!x")
            r = self.client.get(reverse("store:settings"))
            self.assertContains(r, "data-map-picker")
        r = self.client.post(reverse("store:settings"), self.post_data())
        self.assertRedirects(r, reverse("store:settings"))
        store = StoreSettings.current()
        self.assertEqual(store.whatsapp, "6281234567890")
        self.assertEqual(store.latitude, Decimal("-1.250000"))
        self.assertEqual(store.updated_by.username, "sup")
        self.assertEqual(BankAccount.objects.get().holder, "Seelly")
        self.assertTrue(ActivityLog.for_object(store).exists())

    def test_saved_whatsapp_and_bank_show_on_site(self):
        self.client.login(username="adm", password="Pass12345!x")
        self.client.post(reverse("store:settings"), self.post_data())
        r = self.client.get(reverse("customer:about"))
        self.assertContains(r, "wa.me/6281234567890")

    def test_invalid_hours_rejected(self):
        self.client.login(username="adm", password="Pass12345!x")
        r = self.client.post(reverse("store:settings"), self.post_data(open_hour=20, close_hour=8))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Jam tutup harus setelah jam buka")

    def test_delete_bank_account(self):
        acc = BankAccount.objects.create(bank="BRI", number="1", holder="X")
        self.client.login(username="adm", password="Pass12345!x")
        data = self.post_data(**{
            "bank-TOTAL_FORMS": "1", "bank-INITIAL_FORMS": "1", "bank-0-id": str(acc.pk),
            "bank-0-bank": "BRI", "bank-0-number": "1", "bank-0-holder": "X", "bank-0-DELETE": "on",
        })
        self.client.post(reverse("store:settings"), data)
        self.assertFalse(BankAccount.objects.exists())


class StaffRegistrationTests(TestCase):
    def register(self, **override):
        data = {
            "name": "Budi Kurir", "username": "budi", "phone_number": "081234567890",
            "address": "Balikpapan", "role": Role.COURIER, "vehicle": "Honda Beat",
            "plate_number": "kt 1234 ab", "can_carry_pets": "on",
            "password1": "Rahasia!2026x", "password2": "Rahasia!2026x",
        }
        data.update(override)
        return self.client.post(reverse("register_staff"), data)

    def test_register_creates_pending_inactive_account(self):
        admin = make_user("adm", Role.ADMIN)
        r = self.register()
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "account/register_staff_done.html")
        user = User.objects.get(username="budi")
        self.assertEqual(user.approval, Approval.PENDING)
        self.assertFalse(user.is_active)
        self.assertTrue(user.courier_profile.can_carry_pets)
        self.assertEqual(user.courier_profile.plate_number, "KT 1234 AB")
        self.assertTrue(Notification.objects.filter(user=admin).exists())

    def test_cannot_self_register_as_admin(self):
        r = self.register(role=Role.ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="budi").exists())

    def test_cannot_self_register_as_cashier(self):
        r = self.register(role=Role.CASHIER, vehicle="", plate_number="", can_carry_pets="")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "account/register_staff.html")
        self.assertFalse(User.objects.filter(username="budi").exists())
        roles = [code for code, _label in r.context["form"].fields["role"].choices]
        self.assertEqual(roles, [Role.COURIER])

    def test_cannot_self_register_as_groomer(self):
        r = self.register(role=Role.GROOMER, vehicle="", plate_number="", can_carry_pets="")
        self.assertTemplateUsed(r, "account/register_staff.html")
        self.assertFalse(User.objects.filter(username="budi").exists())

    def test_admin_and_superadmin_create_cashier_and_groomer_accounts(self):
        make_user("adm", Role.ADMIN)
        make_user("sup", Role.SUPERADMIN)
        for creator, username, role in (("adm", "kasir_a", Role.CASHIER), ("sup", "kasir_b", Role.CASHIER),
                                        ("adm", "groomer_a", Role.GROOMER), ("sup", "groomer_b", Role.GROOMER)):
            self.client.login(username=creator, password="Pass12345!x")
            self.client.post(reverse("add_employee"), {
                "username": username, "first_name": "Kasir", "last_name": "Baru",
                "phone_number": "081234567891", "role": role, "password": "Rahasia!2026x",
            })
            staff = User.objects.get(username=username)
            self.assertEqual(staff.role, role)
            self.assertTrue(staff.is_active)
            self.client.logout()

    def test_courier_needs_vehicle(self):
        self.register(vehicle="", plate_number="")
        self.assertFalse(User.objects.filter(username="budi").exists())

    def test_pending_cannot_login_until_approved(self):
        make_user("adm", Role.ADMIN)
        self.register()
        r = self.client.post(reverse("login_form"), {"username": "budi", "password": "Rahasia!2026x"})
        self.assertContains(r, "menunggu persetujuan")
        self.client.login(username="adm", password="Pass12345!x")
        budi = User.objects.get(username="budi")
        r = self.client.post(reverse("decide_staff", args=[budi.pk]), {"decision": "approve"})
        self.assertEqual(r.status_code, 302)
        budi.refresh_from_db()
        self.assertTrue(budi.is_active)
        self.assertEqual(budi.approval, Approval.APPROVED)
        self.client.logout()
        self.assertTrue(self.client.login(username="budi", password="Rahasia!2026x"))

    def test_reject(self):
        make_user("adm", Role.ADMIN)
        self.register()
        self.client.login(username="adm", password="Pass12345!x")
        budi = User.objects.get(username="budi")
        self.client.post(reverse("decide_staff", args=[budi.pk]), {"decision": "reject"})
        budi.refresh_from_db()
        self.assertEqual(budi.approval, Approval.REJECTED)
        self.assertFalse(budi.is_active)

    def test_pending_list_visible_to_admin(self):
        make_user("adm", Role.ADMIN)
        self.register()
        self.client.login(username="adm", password="Pass12345!x")
        r = self.client.get(reverse("manage_account") + "?tab=approval")
        self.assertContains(r, "Budi Kurir")
        self.assertEqual(r.context["pending_staff_count"], 1)


class NotificationTests(TestCase):
    def setUp(self):
        self.user = make_user("cus", Role.CUSTOMER)
        self.client.login(username="cus", password="Pass12345!x")

    def test_list_and_open_marks_read(self):
        Notification.send(self.user, "Pesanan dikirim", url="/pesanan-saya/")
        note = Notification.objects.get()
        r = self.client.get(reverse("store:notifications"))
        self.assertContains(r, "Pesanan dikirim")
        self.assertEqual(r.context["unread_notifications"], 1)
        r = self.client.get(reverse("store:open_notification", args=[note.pk]))
        self.assertRedirects(r, "/pesanan-saya/", fetch_redirect_response=False)
        note.refresh_from_db()
        self.assertIsNotNone(note.read_at)

    def test_external_url_not_followed(self):
        Notification.send(self.user, "x", url="https://evil.example.com/")
        note = Notification.objects.get()
        r = self.client.get(reverse("store:open_notification", args=[note.pk]))
        self.assertRedirects(r, reverse("store:notifications"))

    def test_cannot_open_others(self):
        other = make_user("cus2", Role.CUSTOMER)
        Notification.send(other, "rahasia")
        r = self.client.get(reverse("store:open_notification", args=[Notification.objects.get().pk]))
        self.assertEqual(r.status_code, 404)

    def test_read_all(self):
        Notification.send(self.user, "a")
        Notification.send(self.user, "b")
        self.client.post(reverse("store:read_all"))
        self.assertFalse(Notification.objects.unread().exists())

    def test_staff_page_renders(self):
        make_user("kur", Role.COURIER)
        self.client.login(username="kur", password="Pass12345!x")
        r = self.client.get(reverse("store:notifications"))
        self.assertTemplateUsed(r, "store/notifications_staff.html")


class CustomerDashboardTests(TestCase):
    def test_customer_lands_on_dashboard(self):
        make_user("cus", Role.CUSTOMER)
        r = self.client.post(reverse("login_form"), {"username": "cus", "password": "Pass12345!x"})
        self.assertRedirects(r, reverse("customer:dashboard"), fetch_redirect_response=False)
        r = self.client.get(reverse("customer:dashboard"))
        self.assertContains(r, "Dasbor Pelanggan")

    def test_staff_cannot_open_customer_dashboard(self):
        make_user("kas", Role.CASHIER)
        self.client.login(username="kas", password="Pass12345!x")
        self.assertEqual(self.client.get(reverse("customer:dashboard")).status_code, 403)
