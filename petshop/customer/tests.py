import json

from django.test import TestCase
from django.urls import reverse

from account.models import Customer
from product.models import Category, Product


class StorefrontTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.food = Category.objects.create(name=Category.FOOD)
        cls.toys = Category.objects.create(name=Category.EQUIPMENT)
        cls.kibble = Product.objects.create(
            category=cls.food, name="Cat Kibble", purchase_price=30000,
            selling_price=48000, stock=10,
        )
        cls.ball = Product.objects.create(
            category=cls.toys, name="Rubber Ball", purchase_price=5000,
            selling_price=15000, stock=0,
        )
        cls.hidden = Product.objects.create(
            category=cls.food, name="Inactive Item", purchase_price=1000,
            selling_price=2000, stock=5, is_active=False,
        )


class PageTests(StorefrontTestCase):
    def test_home_lists_sellable_products_only(self):
        response = self.client.get(reverse("customer:home"))
        self.assertContains(response, "Cat Kibble")
        self.assertNotContains(response, "Inactive Item")

    def test_shop_filters_by_category_price_and_stock(self):
        url = reverse("customer:shop")
        self.assertContains(self.client.get(url, {"category": "FOOD"}), "Cat Kibble")
        self.assertNotContains(self.client.get(url, {"category": "FOOD"}), "Rubber Ball")
        self.assertNotContains(self.client.get(url, {"in_stock": "1"}), "Rubber Ball")
        self.assertNotContains(self.client.get(url, {"min_price": "20000"}), "Rubber Ball")
        self.assertContains(self.client.get(url, {"q": "ball"}), "Rubber Ball")

    def test_shop_ignores_invalid_filters(self):
        response = self.client.get(
            reverse("customer:shop"),
            {"category": "NOPE", "min_price": "abc", "sort": "bogus"},
        )
        self.assertEqual(response.status_code, 200)

    def test_product_detail(self):
        self.assertEqual(
            self.client.get(reverse("customer:product_detail", args=[self.kibble.pk])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("customer:product_detail", args=[self.hidden.pk])).status_code, 404
        )

    def test_cart_and_checkout_pages(self):
        self.assertEqual(self.client.get(reverse("customer:cart")).status_code, 200)
        self.assertEqual(self.client.get(reverse("customer:checkout")).status_code, 200)


class PlaceOrderTests(StorefrontTestCase):
    def post_order(self, items, **overrides):
        data = {
            "name": "Budi",
            "phone": "+62 812-3456-7890",
            "address": "Jl. Merdeka 1",
            "payment_method": "Bank Transfer",
            "cart_data": json.dumps(items),
        }
        data.update(overrides)
        return self.client.post(reverse("customer:place_order"), data)

    def test_order_creates_customer_and_returns_whatsapp_link(self):
        response = self.post_order([{"id": self.kibble.pk, "quantity": 2}])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["whatsapp_url"].startswith("https://wa.me/"))
        self.assertTrue(Customer.objects.filter(phone_number="081234567890").exists())

    def test_price_comes_from_database(self):
        response = self.post_order([{"id": self.kibble.pk, "quantity": 1, "price": 1}])
        self.assertIn("48.000", response.json()["whatsapp_url"].replace("%2E", "."))

    def test_rejects_more_than_stock(self):
        response = self.post_order([{"id": self.kibble.pk, "quantity": 11}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("cart", response.json()["errors"])

    def test_rejects_empty_cart_and_bad_fields(self):
        response = self.post_order([], name="", phone="abc")
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertIn("name", errors)
        self.assertIn("phone", errors)
        self.assertIn("cart", errors)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("customer:place_order")).status_code, 405)
