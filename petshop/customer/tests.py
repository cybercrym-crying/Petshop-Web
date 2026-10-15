import re

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from account.models import Customer, Role, User
from product.models import Category, Product
from transaction.models import Order


def make_product(name="Whiskas", stock=5, price=12000):
    category, _ = Category.objects.get_or_create(name=Category.FOOD)
    return Product.objects.create(
        category=category, name=name, purchase_price=7000, selling_price=price, stock=stock
    )


class PublicPagesTests(TestCase):
    def test_urls(self):
        self.assertEqual(reverse("customer:home"), "/customer/")
        self.assertEqual(reverse("customer:katalog"), "/customer/shop/")
        self.assertEqual(reverse("customer:about"), "/customer/about/")

    def test_home_renders_with_real_images_not_vectors(self):
        r = self.client.get(reverse("customer:home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Everything Your Pet Needs")
        html = r.content.decode()
        imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
        self.assertGreaterEqual(len(imgs), 7)  # hero, 2 foto besar, 4 kategori
        for src in imgs:
            self.assertRegex(src, r"\.(png|jpe?g|webp)$", f"gambar bukan raster: {src}")
            self.assertTrue(
                finders.find(src.replace("/static/", "", 1)), f"file tidak ditemukan: {src}"
            )

    def test_about_shows_live_stats(self):
        make_product()
        Customer.objects.create(name="Siti", phone_number="0811", address="x")
        r = self.client.get(reverse("customer:about"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["stats"], {"products": 1, "orders": 0, "customers": 1})
        self.assertContains(r, "Our Story")
        self.assertContains(r, "https://wa.me/6281356703075")

    def test_about_counts_only_delivered_orders(self):
        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        cust = Customer.objects.create(name="Siti", phone_number="0811", address="x")
        for status in ("CONFIRMED", "DELIVERED", "DELIVERED"):
            Order.objects.create(
                admin=admin, customer=cust, payment_method="CASH",
                total_payment=1000, order_status=status,
            )
        r = self.client.get(reverse("customer:about"))
        self.assertEqual(r.context["stats"]["orders"], 2)

    def test_shop_lists_products_and_marks_nav(self):
        make_product("Whiskas 70g")
        r = self.client.get(reverse("customer:katalog"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Whiskas 70g")
        self.assertContains(r, 'id="product-grid"')
        self.assertContains(r, 'class="nav-link-custom active">Shop')

    def test_nav_links_between_pages_and_search_goes_to_shop(self):
        for name in ("customer:home", "customer:about", "customer:katalog"):
            r = self.client.get(reverse(name))
            self.assertContains(r, 'href="/customer/shop/"')
            self.assertContains(r, 'href="/customer/about/"')
            self.assertContains(r, 'action="/customer/shop/"')
            self.assertContains(r, 'id="cart-count"')
            self.assertContains(r, 'id="kontak"')  # tujuan tautan Contact Us

    def test_cart_and_checkout_still_load(self):
        self.assertEqual(self.client.get(reverse("customer:cart")).status_code, 200)
        self.assertEqual(self.client.get(reverse("customer:checkout")).status_code, 200)


class DesignUpdateTests(TestCase):
    def raster_imgs(self, response):
        imgs = re.findall(r'<img[^>]+src="([^"]+)"', response.content.decode())
        for src in imgs:
            self.assertRegex(src, r"\.(png|jpe?g|webp)$", f"gambar bukan raster: {src}")
            self.assertTrue(finders.find(src.replace("/static/", "", 1)), f"hilang: {src}")
        return imgs

    def test_home_hero_and_offer_banner(self):
        r = self.client.get(reverse("customer:home"))
        self.assertContains(r, "Healthy Pets, Happier Lives")
        self.assertContains(r, "Get 20% OFF on Selected Pet Products")
        self.assertNotContains(r, "Ready to Order for Your Pet?")

    def test_home_offer_can_be_turned_off(self):
        from unittest import mock

        with mock.patch("customer.views.SPECIAL_OFFER", None):
            r = self.client.get(reverse("customer:home"))
        self.assertNotContains(r, "20% OFF")
        self.assertContains(r, "Ready to Order for Your Pet?")

    def test_about_values_gallery_has_six_real_photos_and_arrows(self):
        r = self.client.get(reverse("customer:about"))
        html = r.content.decode()
        self.assertEqual(html.count('class="sx-vp"'), 6)
        self.assertContains(r, 'id="values-rail"')
        self.assertContains(r, 'id="rail-prev"')
        self.assertContains(r, 'id="rail-next"')
        self.assertGreaterEqual(len(self.raster_imgs(r)), 8)  # hero, kolase, 6 nilai

    def test_about_store_address_only_when_set(self):
        from unittest import mock

        r = self.client.get(reverse("customer:about"))
        self.assertNotContains(r, "Jl. Contoh No. 1")
        with mock.patch("customer.views.STORE_ADDRESS", "Jl. Contoh No. 1"):
            r = self.client.get(reverse("customer:about"))
        self.assertContains(r, "Jl. Contoh No. 1")

    def test_about_breadcrumb_links_home(self):
        r = self.client.get(reverse("customer:about"))
        self.assertContains(r, 'href="/customer/">Home</a> / About Us')
