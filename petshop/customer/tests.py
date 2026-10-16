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
        self.assertEqual(reverse("customer:home"), "/")
        self.assertEqual(reverse("customer:katalog"), "/shop/")
        self.assertEqual(reverse("customer:about"), "/about/")

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
            self.assertContains(r, 'href="/shop/"')
            self.assertContains(r, 'href="/about/"')
            self.assertContains(r, 'action="/shop/"')
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
        self.assertContains(r, 'href="/">Home</a> / About Us')


class PublicMobileNavTests(TestCase):
    def test_every_public_page_has_a_mobile_menu_with_all_links(self):
        for name in ("customer:home", "customer:about", "customer:katalog"):
            r = self.client.get(reverse(name))
            self.assertContains(r, 'id="nav-toggle"')
            self.assertContains(r, 'id="mobile-menu"')
            html = r.content.decode()
            menu = html[html.index('id="mobile-menu"'):]
            for label in ("Home", "Shop", "About Us", "Contact Us"):
                self.assertIn(f">{label}</a>", menu.split("</nav>")[0], f"{name}: {label}")

    def test_shop_header_wraps_and_search_has_two_synced_inputs(self):
        r = self.client.get(reverse("customer:katalog"))
        self.assertEqual(r.content.decode().count('class="search-bar js-search"'), 1)
        self.assertEqual(r.content.decode().count('class="js-search"'), 1)
        self.assertContains(r, "flex-wrap gap-2 mb-4")


class SiteAtRootTests(TestCase):
    def test_root_is_the_new_home_and_old_home_is_gone(self):
        from django.urls import NoReverseMatch

        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Everything Your Pet Needs")
        with self.assertRaises(NoReverseMatch):
            reverse("home")  # rute home lama di app account sudah dihapus

    def test_old_customer_prefix_redirects_permanently(self):
        for old, new in (
            ("/customer/", "/"),
            ("/customer/shop/", "/shop/"),
            ("/customer/about/", "/about/"),
            ("/customer/cart", "/cart"),
            ("/customer/shop/?q=whiskas", "/shop/?q=whiskas"),
        ):
            r = self.client.get(old)
            self.assertEqual(r.status_code, 301, old)
            self.assertEqual(r["Location"], new, old)

    def test_removed_dead_routes_return_404(self):
        for path in ("/catalog", "/pesan", "/dashboard"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_forbidden_page_links_back_to_home(self):
        User.objects.create_user("cr", password="x", role=Role.COURIER)
        self.client.login(username="cr", password="x")
        r = self.client.get("/staff/admin/dashboard")
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, 'href="/"', status_code=403)

    def test_courier_login_goes_to_public_home(self):
        User.objects.create_user("kurir", password="x", role=Role.COURIER)
        r = self.client.post("/login", {"username": "kurir", "password": "x"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
