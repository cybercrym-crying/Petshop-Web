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
        self.assertGreaterEqual(len(imgs), 5)  # hero + 4 foto kategori
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
        for status in ("DIKONFIRMASI", "TERKIRIM", "TERKIRIM"):
            Order.objects.create(
                admin=admin, customer=cust, payment_method="TUNAI",
                total_payment=1000, order_status=status,
            )
        r = self.client.get(reverse("customer:about"))
        self.assertEqual(r.context["stats"]["orders"], 2)

    def test_shop_lists_products_and_marks_nav(self):
        make_product("Whiskas 70g")
        r = self.client.get(reverse("customer:shop"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Whiskas 70g")
        self.assertContains(r, 'class="sn-link active">Belanja')

    def test_nav_links_between_pages_and_search_lives_in_shop_filter(self):
        for name in ("customer:home", "customer:about", "customer:shop"):
            r = self.client.get(reverse(name))
            self.assertContains(r, 'href="/shop/"')
            self.assertContains(r, 'href="/about/"')
            self.assertNotContains(r, 'id="nav-search"')  # cari produk pindah ke filter Belanja
            self.assertContains(r, 'id="cart-count"')
            self.assertContains(r, 'id="kontak"')  # tujuan tautan Contact Us

    def test_product_search_in_shop_filter(self):
        make_product("Whiskas 70g")
        make_product("Pasir Kucing")
        r = self.client.get(reverse("customer:products"), {"q": "whis"})
        self.assertContains(r, 'id="filter-q" name="q" value="whis"')
        names = [p.name for p in r.context["products"]]
        self.assertEqual(names, ["Whiskas 70g"])

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
        from unittest import mock

        # Bawaan: tidak ada promo palsu, banner berisi ajakan memesan biasa.
        r = self.client.get(reverse("customer:home"))
        self.assertContains(r, "Hewan Sehat, Hidup Lebih Bahagia")
        self.assertNotContains(r, "Penawaran Spesial")
        self.assertContains(r, "Siap Memesan untuk Hewan Kesayangan?")
        offer = {"title": "Diskon 20% untuk Produk Pilihan", "text": "Sampai akhir bulan."}
        with mock.patch("customer.views.SPECIAL_OFFER", offer):
            r = self.client.get(reverse("customer:home"))
        self.assertContains(r, "Diskon 20% untuk Produk Pilihan")
        self.assertNotContains(r, "Siap Memesan untuk Hewan Kesayangan?")

    def test_home_offer_can_be_turned_off(self):
        from unittest import mock

        with mock.patch("customer.views.SPECIAL_OFFER", None):
            r = self.client.get(reverse("customer:home"))
        self.assertNotContains(r, "Diskon 20%")
        self.assertContains(r, "Siap Memesan untuk Hewan Kesayangan?")

    def test_about_values_grid_and_real_photos(self):
        r = self.client.get(reverse("customer:about"))
        html = r.content.decode()
        self.assertEqual(html.count('class="value-card"'), 4)
        self.assertContains(r, 'class="values-grid"')
        self.assertGreaterEqual(len(self.raster_imgs(r)), 2)  # hero, kolase

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


PUBLIC_PAGES = ("customer:home", "customer:shop", "customer:about", "customer:wishlist")


def _nav_html(response):
    html = response.content.decode()
    start = html.index('<header class="sn-header">')
    return html[start:html.index("</header>", start) + len("</header>")]


def _without_active_state(nav):
    # Token CSRF & alamat kembali di tombol bahasa memang berbeda tiap halaman.
    nav = re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', "", nav)
    nav = re.sub(r'name="next" value="[^"]*"', "", nav)
    return nav.replace(" active", "").replace(" is-active", "")


class PublicMobileNavTests(TestCase):
    def test_every_public_page_has_a_mobile_menu_with_all_links(self):
        for name in PUBLIC_PAGES:
            r = self.client.get(reverse(name))
            self.assertContains(r, 'id="nav-toggle"')
            self.assertContains(r, 'id="nav-links"')
            nav = _nav_html(r)
            links = nav[nav.index('id="nav-links"'):].split("</div>")[0]
            for label in ("Beranda", "Belanja", "Tentang Kami", "Hubungi Kami"):
                self.assertIn(f">{label}</a>", links, f"{name}: {label}")


class SharedNavbarTests(TestCase):
    def test_navbar_is_identical_on_every_public_page(self):
        navs = {name: _without_active_state(_nav_html(self.client.get(reverse(name)))) for name in PUBLIC_PAGES}
        reference = navs["customer:home"]
        for name, nav in navs.items():
            self.assertEqual(nav, reference, name)

    def test_active_link_follows_the_current_page(self):
        expected = {
            "customer:home": 'class="sn-link active">Beranda',
            "customer:shop": 'class="sn-link active">Belanja',
            "customer:about": 'class="sn-link active">Tentang Kami',
            "customer:wishlist": 'class="sn-icon is-active"',
        }
        for name, marker in expected.items():
            self.assertIn(marker, _nav_html(self.client.get(reverse(name))), name)

    def test_every_public_page_loads_the_shared_navbar_assets(self):
        for name in PUBLIC_PAGES:
            r = self.client.get(reverse(name))
            self.assertContains(r, "customer/css/nav.css")
            self.assertContains(r, "customer/js/nav.js")

    def test_old_navbar_markup_is_gone(self):
        for name in PUBLIC_PAGES:
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotIn("navbar-seelly", html)
            self.assertNotIn('id="mobile-menu"', html)


class WishlistPageTests(TestCase):
    def test_wishlist_has_its_own_url_and_page(self):
        self.assertEqual(reverse("customer:wishlist"), "/favorit/")
        r = self.client.get("/favorit/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Produk Favorit")
        self.assertContains(r, 'id="wishlist-grid"')
        self.assertContains(r, 'id="wishlist-empty"')
        self.assertContains(r, 'data-items-url="/favorit/produk/"')

    def test_navbar_heart_links_to_the_wishlist_page(self):
        r = self.client.get(reverse("customer:shop"))
        self.assertContains(r, 'href="/favorit/"')
        self.assertNotContains(r, "wishlist=1")

    def test_old_wishlist_link_redirects_to_the_new_page(self):
        r = self.client.get("/shop/", {"wishlist": "1"})
        self.assertRedirects(r, "/favorit/", status_code=301, fetch_redirect_response=False)

    def test_shop_page_no_longer_has_a_wishlist_mode(self):
        make_product()
        r = self.client.get("/shop/", {"q": "whis"})
        self.assertNotContains(r, "data-wishlist-mode")
        self.assertNotContains(r, 'id="wishlist-empty"')

    def test_items_endpoint_returns_only_requested_products_newest_first(self):
        first = make_product("Whiskas 70g")
        second = make_product("Royal Canin")
        make_product("Tidak diminta")
        r = self.client.get("/favorit/produk/", {"ids": f"{first.id},{second.id}"})
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Whiskas 70g", html)
        self.assertIn("Royal Canin", html)
        self.assertNotIn("Tidak diminta", html)
        self.assertLess(html.index("Whiskas 70g"), html.index("Royal Canin"))

    def test_items_endpoint_keeps_the_order_of_the_ids(self):
        first = make_product("Whiskas 70g")
        second = make_product("Royal Canin")
        html = self.client.get("/favorit/produk/", {"ids": f"{second.id},{first.id}"}).content.decode()
        self.assertLess(html.index("Royal Canin"), html.index("Whiskas 70g"))

    def test_items_endpoint_ignores_bad_unknown_and_unsellable_ids(self):
        ok = make_product("Whiskas 70g")
        hidden = make_product("Produk Nonaktif", is_active=False)
        r = self.client.get("/favorit/produk/", {"ids": f"abc,-1,9999,{hidden.id},{ok.id},{ok.id}"})
        html = r.content.decode()
        self.assertEqual(html.count('class="product-card"'), 1)
        self.assertIn("Whiskas 70g", html)
        self.assertNotIn("Produk Nonaktif", html)

    def test_items_endpoint_without_ids_is_empty(self):
        make_product()
        r = self.client.get("/favorit/produk/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content.decode().strip(), "")

    def test_items_endpoint_is_not_cached(self):
        r = self.client.get("/favorit/produk/")
        self.assertIn("no-cache", r.headers["Cache-Control"])


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

    def test_courier_login_goes_to_courier_dashboard(self):
        User.objects.create_user("kurir", password="x", role=Role.COURIER)
        r = self.client.post("/login", {"username": "kurir", "password": "x"})
        self.assertRedirects(r, "/staff/courier/dashboard", fetch_redirect_response=False)


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
        make_product("Whiskas 70g")  # category_label FOOD
        html = self.client.get("/shop/").content.decode()
        self.assertIn('chip-category">Makanan<', html)
        self.assertNotIn('chip-category">Food<', html)

    def test_filter_labels(self):
        from customer.templatetags.customer_extras import category_label

        self.assertEqual(category_label("MAKANAN"), "Makanan")
        self.assertEqual(category_label("PERLENGKAPAN"), "Perlengkapan")
        self.assertEqual(category_label("AKSESORIS"), "Aksesori")
        self.assertEqual(category_label("LAINNYA"), "Lainnya")


class HomeShopTests(TestCase):
    """Belanja (/shop/) menampilkan Home Shop: hero, category_label, produk populer."""

    def test_belanja_links_point_to_shop_and_shop_renders_home_shop(self):
        r = self.client.get(reverse("customer:shop"))
        self.assertTemplateUsed(r, "customer/home_shop.html")
        self.assertTemplateNotUsed(r, "customer/catalog.html")
        for name in ("customer:home", "customer:about", "customer:cart"):
            self.assertContains(self.client.get(reverse(name)), 'href="/shop/"')

    def test_sections_and_context(self):
        make_product("Whiskas 70g")
        r = self.client.get(reverse("customer:shop"))
        for marker in ('class="hero ', 'id="categories"', 'id="popular"', 'id="how-to-order"'):
            self.assertContains(r, marker)
        self.assertEqual([c["code"] for c in r.context["categories"]], ["MAKANAN"])
        self.assertEqual(r.context["categories"][0]["count"], 1)
        self.assertEqual([p.name for p in r.context["popular_products"]], ["Whiskas 70g"])
        self.assertIsNone(r.context["results"])
        self.assertContains(r, "Belanja per Kategori")

    def test_category_card_links_to_filter(self):
        make_product()
        self.assertContains(self.client.get("/shop/"), 'href="/produk/?category=MAKANAN"')

    def test_belanja_sekarang_opens_filter_page(self):
        r = self.client.get("/shop/")
        self.assertContains(r, 'class="btn-solid-light">Belanja Sekarang')
        self.assertContains(r, 'href="/produk/"')

    def test_search_and_category_filter(self):
        make_product("Whiskas 70g")
        make_product("Royal Canin")
        r = self.client.get("/shop/", {"q": "whiskas"})
        self.assertEqual([p.name for p in r.context["results"]], ["Whiskas 70g"])
        self.assertContains(r, 'id="product-grid"')
        r = self.client.get("/shop/", {"category": "makanan"})
        self.assertEqual(len(r.context["results"]), 2)
        r = self.client.get("/shop/", {"category": "AKSESORIS"})
        self.assertEqual(r.context["results"], [])
        self.assertContains(r, "Tidak ada produk yang cocok")

    def test_product_detail(self):
        p = make_product("Whiskas 70g", price=12000)
        r = self.client.get(reverse("customer:product_detail", args=[p.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Whiskas 70g")
        self.assertContains(r, "Rp 12.000")
        self.assertContains(r, '<html lang="id">')
        self.assertEqual(self.client.get("/produk/99999/").status_code, 404)


class ProductsPageTests(TestCase):
    """/produk/: filter jenis hewan, category_label, harga, kondisi + urutan (tombol Belanja Sekarang)."""

    def setUp(self):
        self.kitten = make_product("Royal Canin Kitten", price=92000, pet_type="KUCING")
        self.puppy = make_product("Pro Plan Puppy", price=145000, pet_type="ANJING")
        self.generic = make_product("Sisir Bulu", price=25000, cat=Category.EQUIPMENT)  # semua hewan
        self.used = make_product("Kandang Bekas", price=60000, pet_type="KUCING", condition="BEKAS", cat=Category.EQUIPMENT)

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
        self.assertEqual(sorted(self.names(pet="KUCING")), ["Kandang Bekas", "Royal Canin Kitten", "Sisir Bulu"])
        self.assertEqual(sorted(self.names(pet=["KUCING", "ANJING"])), sorted(p.name for p in Product.objects.all()))

    def test_category_condition_and_price_filters(self):
        self.assertEqual(self.names(category="MAKANAN", pet="ANJING"), ["Pro Plan Puppy"])
        self.assertEqual(self.names(condition="BEKAS"), ["Kandang Bekas"])
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
                admin=admin, customer=cust, payment_method="TUNAI", total_payment=1000, order_status=status
            )
            OrderDetail.objects.create(transaction=o, product=product, quantity=qty, unit_price=1000, subtotal=1000 * qty)

        order(OrderStatus.DELIVERED, self.puppy, 3)
        order(OrderStatus.CANCELLED, self.kitten, 50)
        self.assertEqual(self.names()[0], "Pro Plan Puppy")

    def test_heading_follows_selection(self):
        r = self.client.get("/produk/", {"category": "MAKANAN", "pet": "KUCING"})
        self.assertEqual(r.context["title"], "Makanan Kucing")
        self.assertEqual(r.context["blurb"], "Makanan sehat dan lezat untuk kucing kesayangan Anda.")
        self.assertEqual(self.client.get("/produk/", {"pet": "ANJING"}).context["title"], "Produk untuk Anjing")
        self.assertEqual(self.client.get("/produk/", {"q": "sisir"}).context["title"], "Hasil pencarian “sisir”")

    def test_empty_result_and_reset_link(self):
        r = self.client.get("/produk/", {"condition": "BEKAS", "category": "MAKANAN"})
        self.assertContains(r, "Tidak ada produk yang cocok dengan filter Anda.")
        self.assertContains(r, "Atur ulang semua")

    def test_pagination_keeps_filters(self):
        for i in range(14):
            make_product(f"Snack {i:02d}", price=5000 + i, pet_type="KUCING")
        r = self.client.get("/produk/", {"pet": "KUCING", "sort": "name"})
        self.assertEqual(len(r.context["products"]), 12)
        self.assertContains(r, "pet=KUCING&amp;sort=name&amp;page=2")
        self.assertEqual(len(self.client.get("/produk/", {"pet": "KUCING", "page": 2}).context["products"]), 5)

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


class CheckoutConfirmationTests(TestCase):
    def setUp(self):
        self.page = self.client.get(reverse("customer:checkout"))

    def test_page_has_confirmation_dialog(self):
        self.assertContains(self.page, 'id="confirm-dialog"')
        self.assertContains(self.page, "Periksa Pesanan Anda")

    def test_dialog_shows_receiver_data_and_items(self):
        for element_id in (
            "confirm-name",
            "confirm-phone",
            "confirm-address",
            "confirm-payment",
            "confirm-items",
            "confirm-total",
        ):
            self.assertContains(self.page, f'id="{element_id}"')

    def test_send_button_starts_disabled_until_user_confirms(self):
        html = self.page.content.decode()
        self.assertRegex(html, r"data-confirm-send\s+disabled")
        self.assertContains(self.page, 'id="confirm-check"')
        self.assertContains(self.page, "semuanya sudah benar")

    def test_original_order_button_is_still_there(self):
        self.assertContains(self.page, "data-place-order")
        self.assertContains(self.page, "Pesan via WhatsApp")

    def test_confirmation_logic_lives_in_the_static_script(self):
        script = finders.find("customer/js/checkout.js")
        with open(script, encoding="utf-8") as handle:
            code = handle.read()
        self.assertIn("showModal", code)
        self.assertIn("data-confirm-send", code)
        self.assertNotRegex(self.page.content.decode(), r"<script(?![^>]*\bsrc=)")


class TrackOrderTests(TestCase):
    def setUp(self):
        from account.models import Customer, Role, User
        from transaction.models import Order

        self.admin = User.objects.create_user("adm_lacak", password="x", role=Role.ADMIN)
        self.courier = User.objects.create_user(
            "kurir_lacak", password="x", role=Role.COURIER, first_name="Rudi"
        )
        self.customer = Customer.objects.create(
            name="Budi Santoso", phone_number="081200001111", address="Jl. Rahasia 99"
        )
        self.order = Order.objects.create(
            admin=self.admin,
            courier=self.courier,
            customer=self.customer,
            payment_method="TUNAI",
            total_payment=45000,
        )
        # Pengunjung tanpa login: verifikasi 4 digit terakhir nomor WA pemesan dulu.
        self.client.post(reverse("customer:track_detail", args=[self.order.tracking_number]), {"wa4": "1111"})

    def test_stranger_must_verify_last_4_wa_digits(self):
        from django.core.cache import cache

        cache.clear()
        stranger = self.client_class()
        url = reverse("customer:track_detail", args=[self.order.tracking_number])
        locked = stranger.get(url)
        self.assertContains(locked, "4 digit terakhir nomor WhatsApp")
        self.assertNotContains(locked, "Pesanan dikonfirmasi")
        self.assertNotContains(locked, "Budi S****")
        self.assertEqual(stranger.get(reverse("customer:track_location", args=[self.order.tracking_number])).status_code, 403)
        self.assertContains(stranger.post(url, {"wa4": "9999"}), "tidak cocok")
        self.assertRedirects(stranger.post(url, {"wa4": "1111"}), url)
        self.assertContains(stranger.get(url), "Pesanan dikonfirmasi")
        # Tebakan beruntun dikunci 15 menit.
        other = self.client_class()
        for _ in range(5):
            other.post(url, {"wa4": "0000"})
        self.assertContains(other.post(url, {"wa4": "1111"}), "Terlalu banyak percobaan")
        cache.clear()

    def test_empty_form_page_renders(self):
        response = self.client.get(reverse("customer:track"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Masukkan nomor resi")

    def test_unknown_resi_shows_error(self):
        response = self.client.get(reverse("customer:track"), {"resi": "PS-000000-AAAAAA"})
        self.assertContains(response, "Resi tidak ditemukan")

    def test_garbage_resi_shows_error_not_crash(self):
        response = self.client.get(reverse("customer:track"), {"resi": "<script>x</script>"})
        self.assertContains(response, "Resi tidak ditemukan")
        self.assertNotContains(response, "<script>x</script>")

    def test_lookup_by_query_and_by_link(self):
        by_query = self.client.get(
            reverse("customer:track"), {"resi": self.order.tracking_number.lower()}
        )
        by_link = self.client.get(
            reverse("customer:track_detail", args=[self.order.tracking_number])
        )
        for response in (by_query, by_link):
            self.assertContains(response, self.order.tracking_number)
            self.assertContains(response, "Pesanan dikonfirmasi")

    def test_private_data_is_not_exposed(self):
        response = self.client.get(
            reverse("customer:track_detail", args=[self.order.tracking_number])
        )
        self.assertContains(response, "Budi S****")
        self.assertNotContains(response, "Santoso")
        self.assertNotContains(response, "Jl. Rahasia 99")
        self.assertNotContains(response, "081200001111")

    def test_page_is_not_cacheable(self):
        response = self.client.get(
            reverse("customer:track_detail", args=[self.order.tracking_number])
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_delivered_order_shows_proof_photo(self):
        import io
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from PIL import Image

        media = tempfile.mkdtemp(prefix="petshop-test-media-")
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), "blue").save(buffer, "JPEG")
        with override_settings(MEDIA_ROOT=media):
            self.order.mark_on_delivery(self.courier)
            self.order.mark_delivered(
                photo=SimpleUploadedFile("x.jpg", buffer.getvalue(), "image/jpeg"),
                note="Titip di pos satpam",
            )
            response = self.client.get(
                reverse("customer:track_detail", args=[self.order.tracking_number])
            )
        self.assertContains(response, "Bukti pengiriman")
        self.assertContains(response, self.order.delivery_photo.url)
        self.assertContains(response, "Titip di pos satpam")
        self.assertContains(response, "Rudi")

    def test_in_delivery_order_has_no_proof_section(self):
        self.order.mark_on_delivery(self.courier)
        response = self.client.get(
            reverse("customer:track_detail", args=[self.order.tracking_number])
        )
        self.assertContains(response, "Sedang dikirim kurir")
        self.assertNotContains(response, "Bukti pengiriman")

    def test_cancelled_order_shows_cancel_notice(self):
        self.order.cancel()
        response = self.client.get(
            reverse("customer:track_detail", args=[self.order.tracking_number])
        )
        self.assertContains(response, "Pesanan ini dibatalkan")
        self.assertNotContains(response, "Bukti pengiriman")

    def test_nav_has_track_link(self):
        response = self.client.get(reverse("customer:home"))
        self.assertContains(response, reverse("customer:track"))


class CustomerAreaTests(TestCase):
    """Landing page untuk pengunjung; pelanggan yang masuk punya area & dasbor sendiri."""

    def setUp(self):
        self.customer = Customer.objects.create(username="ayu", name="Ayu", phone_number="081299990000", address="x")
        self.client.force_login(self.customer)

    def test_logged_in_customer_skips_the_landing_page(self):
        self.assertRedirects(self.client.get(reverse("customer:home")), reverse("customer:dashboard"))

    def test_customer_pages_use_the_customer_area_layout(self):
        for name in ("customer:dashboard", "customer:shop", "customer:my_orders", "service:my_bookings",
                     "service:my_pets", "customer:account", "store:complaints", "customer:cart"):
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn('id="ca-side"', html, name)
            self.assertIn("customer/css/app.css", html, name)
            self.assertNotIn('id="nav-links"', html, name)  # menu promosi landing page tidak tampil
            self.assertNotIn('class="site-footer"', html, name)

    def test_dashboard_quick_tiles_and_folded_bank_details(self):
        order = Order.objects.create(customer=self.customer, payment_method="TRANSFER", total_payment=50000)
        html = self.client.get(reverse("customer:dashboard")).content.decode()
        tiles = re.search(r'<nav class="dash-tiles".*?</nav>', html, re.S).group(0)
        for name in ("customer:shop", "service:catalog", "service:my_pets", "customer:track"):
            self.assertIn(f'href="{reverse(name)}', tiles, name)
        # Rincian rekening dilipat, tombol Bayar langsung ke halaman kirim bukti.
        self.assertIn(f'<details class="dash-unpaid" id="bayar-{order.pk}">', html)
        self.assertIn(f'href="{reverse("customer:payment_proof", args=[order.pk])}">Bayar</a>', html)

    def test_active_menu_follows_the_current_page(self):
        html = self.client.get(reverse("customer:my_orders")).content.decode()
        self.assertRegex(html, r'class="ca-link is-active"[^>]*><i class="fas fa-box"')

    def test_visitor_still_sees_the_landing_page(self):
        self.client.logout()
        html = self.client.get(reverse("customer:home")).content.decode()
        self.assertIn('id="nav-links"', html)
        self.assertNotIn('id="ca-side"', html)

    def test_landing_shows_order_steps_and_store_visit_info(self):
        from store.models import StoreSettings
        self.client.logout()
        store = StoreSettings.current()
        html = self.client.get(reverse("customer:home")).content.decode()
        self.assertEqual(len(re.findall(r'class="sx-steps__no"', html)), 4)
        self.assertIn(f'href="{reverse("register")}"', html)
        self.assertIn(store.address, html)
        self.assertIn(store.hours_display, html)
        self.assertIn(f'href="{store.whatsapp_link}"', html)

    def test_checkout_steps_and_numbered_sections_for_member_and_guest(self):
        member = self.client.get(reverse("customer:checkout")).content.decode()
        self.assertIn('class="cx-steps"', member)
        self.assertEqual(len(re.findall(r'class="cx-num"', member)), 4)
        self.assertIn("data-co-subtotal", member)
        self.assertIn("data-co-submit", member)
        self.client.logout()
        guest = self.client.get(reverse("customer:checkout")).content.decode()
        self.assertIn('class="cx-steps"', guest)
        self.assertEqual(len(re.findall(r'class="cx-num"', guest)), 3)
        # Kolom yang dibaca checkout.js tetap berada di dalam #checkout-form.
        form = re.search(r'<form id="checkout-form".*?</form>', guest, re.S).group(0)
        for field in ('name="nama"', 'name="no_wa"', 'name="alamat"'):
            self.assertIn(field, form)
        self.assertIn(f'href="{reverse("login_form")}?next=', guest)

    def test_staff_browsing_the_shop_keep_the_public_layout(self):
        self.client.force_login(User.objects.create_user("adm", password="x", role=Role.ADMIN))
        self.assertEqual(self.client.get(reverse("customer:home")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("customer:shop")), 'id="ca-side"')


class ProductTrackingMapTests(TestCase):
    """Pelanggan melihat peta pengiriman sejak pesanan dibuat, posisi kurir saat diantar."""

    def setUp(self):
        from decimal import Decimal

        from transaction.tests import make_product

        self.customer = Customer.objects.create(username="ayu", name="Ayu", phone_number="081299990001", address="x")
        product = make_product("Pakan Uji", stock=5)
        self.order = Order.place_online(
            self.customer, [(product.pk, 1)], "TUNAI", address="Jl. Melur 5",
            location=(Decimal("-1.255400"), Decimal("116.831200")),
        )

    def test_waiting_order_already_has_a_map(self):
        self.client.force_login(self.customer)
        page = self.client.get(reverse("customer:track_detail", args=[self.order.tracking_number]))
        self.assertContains(page, "data-track-live")
        self.assertContains(page, "vendor/leaflet/leaflet.js")
        data = self.client.get(reverse("customer:track_location", args=[self.order.tracking_number])).json()
        self.assertFalse(data["live"])
        self.assertIn("store", data)
        self.assertIn("destination", data)  # pemilik melihat titik rumahnya

    def test_strangers_see_the_store_but_not_the_address(self):
        url = reverse("customer:track_location", args=[self.order.tracking_number])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.post(reverse("customer:track_detail", args=[self.order.tracking_number]), {"wa4": "0001"})
        data = self.client.get(url).json()
        self.assertIn("store", data)
        self.assertNotIn("destination", data)


class DarkModeTests(TestCase):
    """Mode gelap di semua halaman toko dan menu samping yang bisa diciutkan."""

    def setUp(self):
        self.user = Customer.objects.create(username="gelap", name="Gelap", phone_number="081299990001", address="x")

    def test_dark_css_files_are_up_to_date(self):
        from common.dark_css import build

        for path, content in build().items():
            self.assertTrue(path.exists(), f"{path.name} belum dibuat: python manage.py build_dark_css")
            self.assertEqual(path.read_text(encoding="utf-8"), content, f"{path.name} kedaluwarsa: python manage.py build_dark_css")

    def test_every_store_page_loads_theme_script_toggle_and_dark_css(self):
        pages = [reverse("customer:home"), reverse("customer:shop"), reverse("customer:about"), reverse("login_form"), reverse("register")]
        for url in pages:
            html = self.client.get(url).content.decode()
            self.assertIn("js/theme_boot.js", html, url)
            self.assertIn("data-theme-toggle", html, url)
            for css in re.findall(r"static/([\w/]+)\.css", html):
                if finders.find(f"{css}-dark.css"):
                    self.assertIn(f"{css}-dark.css", html, f"{url}: {css}")
        self.client.force_login(self.user)
        for url in (reverse("customer:dashboard"), reverse("customer:my_orders"), reverse("service:my_bookings")):
            html = self.client.get(url).content.decode()
            self.assertIn("data-theme-toggle", html, url)
            for css in re.findall(r"static/([\w/]+)\.css", html):
                if finders.find(f"{css}-dark.css"):
                    self.assertIn(f"{css}-dark.css", html, f"{url}: {css}")

    def test_sidebar_toggle_has_open_and_close_labels(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("customer:dashboard")).content.decode()
        self.assertRegex(html, r'class="sn-icon ca-menu-btn"[^>]*data-label-open="[^"]+"\s+data-label-close="[^"]+"')
        css = open(finders.find("customer/css/app.css"), encoding="utf-8").read()
        self.assertIn(".ca-collapsed .ca-app", css)
