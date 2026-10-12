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
        self.edit(self.admin, Role.COURIR)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_can_change_other_role(self):
        other = User.objects.create_user("o", password="x", role=Role.COURIR, phone_number="08")
        self.edit(other, Role.ADMIN)
        other.refresh_from_db()
        self.assertEqual(other.role, Role.ADMIN)

    def test_add_employee_error_has_no_html(self):
        r = self.client.post(
            "/staff/admin/employee/add/",
            {"username": "n", "role": Role.COURIR, "phone_number": "08"},  # tanpa password
        )
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(msgs)
        self.assertFalse(any("<" in m for m in msgs))
