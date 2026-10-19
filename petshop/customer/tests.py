import re

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from account.models import Customer, Role, User
from product.models import Category, Product
from transaction.models import Order


def make_product(name="Whiskas", stock=5, price=12000, cat=Category.FOOD, **extra):
    category, _ = Category.objects.get_or_create(name=cat)
    return Product.objects.create(
        category=category, name=name, purchase_price=7000, selling_price=price, stock=stock, **extra
    )


class PublicPagesTests(TestCase):
    def test_urls(self):
        self.assertEqual(reverse("customer:home"), "/")
        self.assertEqual(reverse("customer:shop"), "/shop/")
        self.assertEqual(reverse("customer:about"), "/about/")

    def test_home_renders_with_real_images_not_vectors(self):
        r = self.client.get(reverse("customer:home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Semua Kebutuhan Hewan Peliharaan")
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
        self.assertContains(r, "Kisah Kami")
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
        r = self.client.get(reverse("customer:shop"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Whiskas 70g")
        self.assertContains(r, 'class="nav-link-item active">Belanja')

    def test_nav_links_between_pages_and_search_goes_to_shop(self):
        for name in ("customer:home", "customer:about", "customer:shop"):
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
        self.assertContains(r, "Hewan Sehat, Hidup Lebih Bahagia")
        self.assertContains(r, "Diskon 20% untuk Produk Pilihan")
        self.assertNotContains(r, "Siap Memesan untuk Hewan Kesayangan?")

    def test_home_offer_can_be_turned_off(self):
        from unittest import mock

        with mock.patch("customer.views.SPECIAL_OFFER", None):
            r = self.client.get(reverse("customer:home"))
        self.assertNotContains(r, "Diskon 20%")
        self.assertContains(r, "Siap Memesan untuk Hewan Kesayangan?")

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
        self.assertContains(r, 'href="/">Beranda</a> / Tentang Kami')


class PublicMobileNavTests(TestCase):
    def test_every_public_page_has_a_mobile_menu_with_all_links(self):
        for name in ("customer:home", "customer:about"):
            r = self.client.get(reverse(name))
            self.assertContains(r, 'id="nav-toggle"')
            self.assertContains(r, 'id="mobile-menu"')
            html = r.content.decode()
            menu = html[html.index('id="mobile-menu"'):]
            for label in ("Beranda", "Belanja", "Tentang Kami", "Hubungi Kami"):
                self.assertIn(f">{label}</a>", menu.split("</nav>")[0], f"{name}: {label}")

    def test_shop_has_menu_toggle_and_all_nav_links(self):
        r = self.client.get(reverse("customer:shop"))
        self.assertContains(r, 'id="nav-toggle"')
        self.assertContains(r, 'id="nav-links"')
        html = r.content.decode()
        nav = html[html.index('id="nav-links"'):].split("</div>")[0]
        for label in ("Beranda", "Belanja", "Tentang Kami", "Hubungi Kami"):
            self.assertIn(f">{label}</a>", nav, label)


class SiteAtRootTests(TestCase):
    def test_root_is_the_new_home_and_old_home_is_gone(self):
        from django.urls import NoReverseMatch

        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Semua Kebutuhan Hewan Peliharaan")
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


class WorkingSiteTests(TestCase):
    """Penjaga untuk bug yang ditemukan: rute rusak, nama URL tidak cocok, dan dua Home."""

    LIVE_TEMPLATES = (
        "home.html", "about.html", "home_shop.html", "product_detail.html",
        "_product_card.html", "base.html", "cart.html", "checkout.html",
        "_site_nav.html", "_site_footer.html",
    )

    def test_every_public_url_loads(self):
        for path in ("/", "/shop/", "/about/", "/cart", "/checkout"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_every_url_name_used_in_live_templates_exists(self):
        import os

        from django.urls import NoReverseMatch

        base = os.path.join(os.path.dirname(__file__), "templates", "customer")
        names = set()
        for name in self.LIVE_TEMPLATES:
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                names |= set(re.findall(r"{%\s*url\s+['\"]([\w:]+)['\"]", fh.read()))
        self.assertTrue(names, "tidak ada tag url yang ditemukan")
        for n in sorted(names):
            try:
                try:
                    reverse(n)
                except NoReverseMatch:
                    reverse(n, args=[1])  # rute dengan parameter (mis. detail produk)
            except NoReverseMatch:
                self.fail(f"nama URL '{n}' dipakai template tapi tidak ada di urls.py")

    def test_there_is_only_one_home_and_it_is_the_customer_one(self):
        from django.template import TemplateDoesNotExist
        from django.template.loader import get_template

        with self.assertRaises(TemplateDoesNotExist):
            get_template("index.html")  # Home lama di app account sudah dihapus
        self.assertEqual(reverse("customer:home"), "/")
        self.assertContains(self.client.get("/"), "Semua Kebutuhan Hewan Peliharaan")

    def test_public_pages_are_in_indonesian(self):
        for path in ("/", "/shop/", "/about/", "/cart", "/checkout"):
            r = self.client.get(path)
            self.assertContains(r, '<html lang="id">', msg_prefix=path)
        shop = self.client.get("/shop/").content.decode()
        for old in ("Add to Cart", "Out of stock", "View Cart", "Popular Products"):
            self.assertNotIn(old, shop)
        self.assertIn("Lihat Keranjang", shop)
        checkout = self.client.get("/checkout").content.decode()
        self.assertIn("Bayar di Tempat (COD)", checkout)
        self.assertIn("Pesan via WhatsApp", checkout)

    def test_shop_shows_prices_with_dot_separator(self):
        make_product("Whiskas 70g", price=12000)
        self.assertContains(self.client.get("/shop/"), "Rp 12.000")


class CategoryLabelTests(TestCase):
    def test_category_chip_is_in_indonesian(self):
        make_product("Whiskas 70g")  # kategori FOOD
        html = self.client.get("/shop/").content.decode()
        self.assertIn('chip-category">Makanan<', html)
        self.assertNotIn('chip-category">Food<', html)

    def test_filter_labels(self):
        from customer.templatetags.customer_extras import kategori

        self.assertEqual(kategori("FOOD"), "Makanan")
        self.assertEqual(kategori("EQUIPMENT"), "Perlengkapan")
        self.assertEqual(kategori("ACCESSORIES"), "Aksesori")
        self.assertEqual(kategori("LAINNYA"), "Lainnya")


class HomeShopTests(TestCase):
    """Belanja (/shop/) menampilkan Home Shop: hero, kategori, produk populer."""

    def test_belanja_links_point_to_shop_and_shop_renders_home_shop(self):
        r = self.client.get(reverse("customer:shop"))
        self.assertTemplateUsed(r, "customer/home_shop.html")
        self.assertTemplateNotUsed(r, "customer/catalog.html")
        for name in ("customer:home", "customer:about", "customer:cart"):
            self.assertContains(self.client.get(reverse(name)), 'href="/shop/"')

    def test_sections_and_context(self):
        make_product("Whiskas 70g")
        r = self.client.get(reverse("customer:shop"))
        for marker in ('class="hero"', 'id="categories"', 'id="popular"', 'id="how-to-order"'):
            self.assertContains(r, marker)
        self.assertEqual([c["code"] for c in r.context["categories"]], ["FOOD"])
        self.assertEqual(r.context["categories"][0]["count"], 1)
        self.assertEqual([p.name for p in r.context["popular_products"]], ["Whiskas 70g"])
        self.assertIsNone(r.context["results"])
        self.assertContains(r, "Belanja per Kategori")

    def test_category_card_links_to_filter(self):
        make_product()
        self.assertContains(self.client.get("/shop/"), 'href="/produk/?category=FOOD"')

    def test_belanja_sekarang_opens_filter_page(self):
        r = self.client.get("/shop/")
        self.assertContains(r, 'href="/produk/" class="btn-primary-seelly btn-lg">Belanja Sekarang')

    def test_search_and_category_filter(self):
        make_product("Whiskas 70g")
        make_product("Royal Canin")
        r = self.client.get("/shop/", {"q": "whiskas"})
        self.assertEqual([p.name for p in r.context["results"]], ["Whiskas 70g"])
        self.assertContains(r, 'id="product-grid"')
        r = self.client.get("/shop/", {"category": "food"})
        self.assertEqual(len(r.context["results"]), 2)
        r = self.client.get("/shop/", {"category": "ACCESSORIES"})
        self.assertEqual(r.context["results"], [])
        self.assertContains(r, "Tidak ada produk yang cocok")

    def test_wishlist_mode(self):
        make_product()
        r = self.client.get("/shop/", {"wishlist": "1"})
        self.assertContains(r, "data-wishlist-mode")
        self.assertContains(r, 'id="wishlist-empty"')

    def test_product_detail(self):
        p = make_product("Whiskas 70g", price=12000)
        r = self.client.get(reverse("customer:product_detail", args=[p.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Whiskas 70g")
        self.assertContains(r, "Rp 12.000")
        self.assertContains(r, '<html lang="id">')
        self.assertEqual(self.client.get("/produk/99999/").status_code, 404)


class ProductsPageTests(TestCase):
    """/produk/: filter jenis hewan, kategori, harga, kondisi + urutan (tombol Belanja Sekarang)."""

    def setUp(self):
        self.kitten = make_product("Royal Canin Kitten", price=92000, pet_type="CAT")
        self.puppy = make_product("Pro Plan Puppy", price=145000, pet_type="DOG")
        self.generic = make_product("Sisir Bulu", price=25000, cat=Category.GROOMING)  # semua hewan
        self.used = make_product("Kandang Bekas", price=60000, pet_type="CAT", condition="USED", cat=Category.EQUIPMENT)

    def names(self, **params):
        r = self.client.get(reverse("customer:products"), params)
        self.assertEqual(r.status_code, 200)
        return [p.name for p in r.context["products"]]

    def test_page_renders_filter_groups_and_cards(self):
        r = self.client.get("/produk/")
        self.assertTemplateUsed(r, "customer/products.html")
        for marker in ("Jenis Hewan", "Kategori", "Harga", "Kondisi", 'id="sort-select"', "Terapkan Filter"):
            self.assertContains(r, marker)
        self.assertContains(r, "Tambah ke Keranjang")
        self.assertEqual(r.context["title"], "Semua Produk")
        self.assertEqual(r.context["total"], 4)

    def test_pet_filter_keeps_all_pet_products(self):
        self.assertEqual(sorted(self.names(pet="CAT")), ["Kandang Bekas", "Royal Canin Kitten", "Sisir Bulu"])
        self.assertEqual(sorted(self.names(pet=["CAT", "DOG"])), sorted(p.name for p in Product.objects.all()))

    def test_category_condition_and_price_filters(self):
        self.assertEqual(self.names(category="FOOD", pet="DOG"), ["Pro Plan Puppy"])
        self.assertEqual(self.names(condition="USED"), ["Kandang Bekas"])
        self.assertEqual(sorted(self.names(min_price="30000", max_price="100000")), ["Kandang Bekas", "Royal Canin Kitten"])
        # min > max ditukar, nilai ngawur diabaikan
        self.assertEqual(len(self.names(min_price="100000", max_price="30000")), 2)
        self.assertEqual(len(self.names(min_price="abc", pet="NAGA")), 4)

    def test_sort_options(self):
        self.assertEqual(self.names(sort="price_asc")[0], "Sisir Bulu")
        self.assertEqual(self.names(sort="price_desc")[0], "Pro Plan Puppy")
        self.assertEqual(self.names(sort="name")[0], "Kandang Bekas")
        self.assertEqual(len(self.names(sort="ngawur")), 4)

    def test_popular_sort_counts_sold_units_and_ignores_cancelled(self):
        from transaction.models import OrderDetail, OrderStatus

        admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        cust = Customer.objects.create(name="Budi", phone_number="0812", address="x")

        def order(status, product, qty):
            o = Order.objects.create(
                admin=admin, customer=cust, payment_method="CASH", total_payment=1000, order_status=status
            )
            OrderDetail.objects.create(transaction=o, product=product, quantity=qty, unit_price=1000, subtotal=1000 * qty)

        order(OrderStatus.DELIVERED, self.puppy, 3)
        order(OrderStatus.CANCELLED, self.kitten, 50)
        self.assertEqual(self.names()[0], "Pro Plan Puppy")

    def test_heading_follows_selection(self):
        r = self.client.get("/produk/", {"category": "FOOD", "pet": "CAT"})
        self.assertEqual(r.context["title"], "Makanan Kucing")
        self.assertEqual(r.context["blurb"], "Makanan sehat dan lezat untuk kucing kesayangan Anda.")
        self.assertEqual(self.client.get("/produk/", {"pet": "DOG"}).context["title"], "Produk untuk Anjing")
        self.assertEqual(self.client.get("/produk/", {"q": "sisir"}).context["title"], "Hasil pencarian “sisir”")

    def test_empty_result_and_reset_link(self):
        r = self.client.get("/produk/", {"condition": "USED", "category": "FOOD"})
        self.assertContains(r, "Tidak ada produk yang cocok dengan filter Anda.")
        self.assertContains(r, "Atur ulang semua")

    def test_pagination_keeps_filters(self):
        for i in range(14):
            make_product(f"Snack {i:02d}", price=5000 + i, pet_type="CAT")
        r = self.client.get("/produk/", {"pet": "CAT", "sort": "name"})
        self.assertEqual(len(r.context["products"]), 12)
        self.assertContains(r, "pet=CAT&amp;sort=name&amp;page=2")
        self.assertEqual(len(self.client.get("/produk/", {"pet": "CAT", "page": 2}).context["products"]), 5)

    def test_hidden_and_unpriced_products_are_not_listed(self):
        make_product("Tanpa Harga", price=None)
        make_product("Nonaktif", is_active=False)
        self.assertEqual(len(self.names()), 4)

    def test_page_is_indonesian_and_has_nav(self):
        html = self.client.get("/produk/").content.decode()
        self.assertIn('<html lang="id">', html)
        for english in ("Add to Cart", "Pet Type", "Apply Filters", "Sort by"):
            self.assertNotIn(english, html)
        self.assertIn('href="/shop/"', html)
