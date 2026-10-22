from django.test import TestCase
from django.urls import reverse

from account.models import Customer, Role, User
from transaction.models import Order, OrderStatus


def make_courier(username):
    return User.objects.create_user(username, password="x", role=Role.COURIER)


def make_order(courier, status):
    admin = User.objects.get_or_create(
        username="admin_board", defaults={"role": Role.ADMIN}
    )[0]
    customer, _ = Customer.objects.get_or_create(
        phone_number="0811", defaults={"name": "Budi", "address": "Jl. Mawar 1"}
    )
    return Order.objects.create(
        admin=admin,
        courier=courier,
        customer=customer,
        order_status=status,
        payment_method="TUNAI",
    )


class CourierBoardTests(TestCase):
    def setUp(self):
        self.courier = make_courier("kurir_a")
        self.client.force_login(self.courier)
        self.url = reverse("courier:dashboard")

    def test_counts_are_split_by_status(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        response = self.client.get(self.url)
        self.assertEqual(response.context["total_pending"], 2)
        self.assertEqual(response.context["total_on_delivery"], 1)
        self.assertEqual(response.context["total_delivered"], 1)

    def test_default_list_is_pending_only(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        response = self.client.get(self.url)
        self.assertEqual(response.context["current"], "pending")
        self.assertEqual(len(response.context["current_orders"]), 1)
        self.assertEqual(
            response.context["current_orders"][0].order_status, OrderStatus.CONFIRMED
        )

    def test_each_status_shows_only_its_own_orders(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        make_order(self.courier, OrderStatus.DELIVERED)
        expected = {"pending": 1, "on_delivery": 2, "done": 1}
        for status, count in expected.items():
            response = self.client.get(self.url, {"status": status})
            self.assertEqual(response.context["current"], status)
            self.assertEqual(len(response.context["current_orders"]), count)

    def test_unknown_status_falls_back_to_pending(self):
        response = self.client.get(self.url, {"status": "apa-saja"})
        self.assertEqual(response.context["current"], "pending")

    def test_done_list_is_limited_and_links_to_history(self):
        for _ in range(12):
            make_order(self.courier, OrderStatus.DELIVERED)
        response = self.client.get(self.url, {"status": "done"})
        self.assertEqual(len(response.context["current_orders"]), response.context["done_limit"])
        self.assertEqual(response.context["total_delivered"], 12)
        self.assertContains(response, "Lihat semua riwayat")

    def test_other_couriers_orders_are_not_shown(self):
        other = make_courier("kurir_b")
        make_order(other, OrderStatus.CONFIRMED)
        response = self.client.get(self.url)
        self.assertEqual(response.context["total_pending"], 0)

    def test_stat_boxes_link_to_each_status(self):
        response = self.client.get(self.url)
        for status in ("pending", "on_delivery", "done"):
            self.assertContains(response, f"?status={status}")

    def test_card_button_matches_the_status(self):
        make_order(self.courier, OrderStatus.CONFIRMED)
        make_order(self.courier, OrderStatus.ON_DELIVERY)
        pending = self.client.get(self.url, {"status": "pending"})
        self.assertContains(pending, "Mulai Kirim")
        self.assertNotContains(pending, "Selesaikan")
        on_delivery = self.client.get(self.url, {"status": "on_delivery"})
        self.assertContains(on_delivery, "Selesaikan")
        self.assertNotContains(on_delivery, "Mulai Kirim")

    def test_start_and_finish_delivery(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        url = reverse("courier:update_status", args=[order.pk])
        self.client.post(url, {"action": "on_delivery", "status": "pending"})
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ON_DELIVERY)
        self.client.post(url, {"action": "delivered", "status": "on_delivery"})
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)

    def test_action_returns_to_the_list_it_came_from(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery", "status": "pending"},
        )
        self.assertRedirects(response, f"{self.url}?status=pending")

    def test_return_status_is_whitelisted(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery", "status": "https://contoh.com"},
        )
        self.assertRedirects(response, f"{self.url}?status=pending")

    def test_repeated_action_shows_message_instead_of_error(self):
        order = make_order(self.courier, OrderStatus.DELIVERED)
        url = reverse("courier:update_status", args=[order.pk])
        response = self.client.post(url, {"action": "on_delivery"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tidak bisa diubah")

    def test_courier_cannot_update_someone_elses_order(self):
        other = make_courier("kurir_c")
        order = make_order(other, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]), {"action": "on_delivery"}
        )
        self.assertEqual(response.status_code, 404)

    def test_success_message_is_shown_once(self):
        order = make_order(self.courier, OrderStatus.CONFIRMED)
        response = self.client.post(
            reverse("courier:update_status", args=[order.pk]),
            {"action": "on_delivery", "status": "pending"},
            follow=True,
        )
        self.assertContains(response, f"Order #{order.pk} sedang dikirim.", count=1)
