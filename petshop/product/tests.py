from django.test import TestCase
from account.models import User, Role
from .models import Category, Product, StockMutation, MutationType, InsufficientStock


def make_product(stock=5, selling_price=15000, is_active=True, name="Whiskas"):
    category, _ = Category.objects.get_or_create(name=Category.FOOD)
    return Product.objects.create(
        category=category,
        name=name,
        purchase_price=10000,
        selling_price=selling_price,
        stock=stock,
        is_active=is_active,
    )


class SellableTests(TestCase):
    def test_sellable_filters_inactive_and_no_price(self):
        ok = make_product(name="ok")
        make_product(name="inactive", is_active=False)
        make_product(name="noprice", selling_price=None)
        self.assertEqual(list(Product.objects.sellable()), [ok])


class ApplyMutationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a", password="x", role=Role.ADMIN)

    def test_in_adds_stock_and_logs(self):
        p = make_product(stock=5)
        p.apply_mutation(MutationType.IN, 3, user=self.user, note="restock")
        p.refresh_from_db()
        self.assertEqual(p.stock, 8)
        self.assertEqual(p.mutations.count(), 1)

    def test_out_reduces_stock(self):
        p = make_product(stock=5)
        p.apply_mutation(MutationType.OUT, 2)
        p.refresh_from_db()
        self.assertEqual(p.stock, 3)

    def test_out_too_much_raises_and_changes_nothing(self):
        p = make_product(stock=2)
        with self.assertRaises(InsufficientStock):
            p.apply_mutation(MutationType.OUT, 3)
        p.refresh_from_db()
        self.assertEqual(p.stock, 2)
        self.assertEqual(StockMutation.objects.count(), 0)


class SellingPriceFormTests(TestCase):
    def test_below_purchase_price_rejected(self):
        from .form import SellingPriceForm
        p = make_product(selling_price=15000)  # purchase_price 10000
        form = SellingPriceForm({"selling_price": 9000}, instance=p)
        self.assertFalse(form.is_valid())
        self.assertIn("selling_price", form.errors)

    def test_equal_and_empty_allowed(self):
        from .form import SellingPriceForm
        p = make_product(selling_price=15000)
        self.assertTrue(SellingPriceForm({"selling_price": 10000}, instance=p).is_valid())
        self.assertTrue(SellingPriceForm({"selling_price": ""}, instance=p).is_valid())


class ManageProductFilterTests(TestCase):
    def test_non_numeric_category_does_not_crash(self):
        User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.client.login(username="adm", password="x")
        self.assertEqual(self.client.get("/staff/admin/manage_product/?category=abc").status_code, 200)


class StockPagesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.client.login(username="adm", password="x")
        self.p = make_product(stock=5)

    def test_pages_render(self):
        for url in ["/list", f"/{self.p.pk}/price", "/stock-mutation", f"/stock-mutation?product={self.p.pk}"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_record_stock_in_via_page(self):
        self.client.post(
            "/stock-mutation",
            {"product": self.p.pk, "mutationType": "MASUK", "quantity": 4, "note": "restock"},
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 9)
        self.assertContains(self.client.get("/list"), "restock")

    def test_out_over_stock_shows_error_and_keeps_stock(self):
        r = self.client.post(
            "/stock-mutation",
            {"product": self.p.pk, "mutationType": "KELUAR", "quantity": 99, "note": ""},
        )
        self.assertEqual(r.status_code, 200)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)

    def test_zero_quantity_rejected(self):
        self.client.post(
            "/stock-mutation",
            {"product": self.p.pk, "mutationType": "MASUK", "quantity": 0, "note": ""},
        )
        self.assertEqual(StockMutation.objects.count(), 0)

    def test_set_price_page_saves(self):
        self.client.post(f"/{self.p.pk}/price", {"selling_price": 20000})
        self.p.refresh_from_db()
        self.assertEqual(self.p.selling_price, 20000)


class StockListFilterTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.client.login(username="adm", password="x")
        self.ok = make_product(stock=50, name="Aman")
        self.low = make_product(stock=3, name="Menipis")
        self.empty = make_product(stock=0, name="Habis")
        self.noprice = make_product(stock=20, selling_price=None, name="TanpaHarga")

    def names(self, **params):
        r = self.client.get("/list", params)
        self.assertEqual(r.status_code, 200)
        return [p.name for p in r.context["productList"]], r

    def test_counts_and_restock_needed(self):
        _, r = self.names()
        self.assertEqual(
            r.context["counts"], {"all": 4, "low": 1, "empty": 1, "noprice": 1}
        )
        self.assertEqual(r.context["restock_needed"], 2)

    def test_filters(self):
        self.assertEqual(self.names(filter="low")[0], ["Menipis"])
        self.assertEqual(self.names(filter="empty")[0], ["Habis"])
        self.assertEqual(self.names(filter="noprice")[0], ["TanpaHarga"])
        self.assertEqual(len(self.names(filter="ngawur")[0]), 4)  # filter tak dikenal diabaikan

    def test_search_combines_with_filter(self):
        self.assertEqual(self.names(q="hab")[0], ["Habis"])
        self.assertEqual(self.names(filter="low", q="hab")[0], [])

    def test_margin_and_stock_state(self):
        _, r = self.names()
        by = {p.name: p for p in r.context["productList"]}
        self.assertEqual(by["Aman"].margin, 5000)
        self.assertIsNone(by["TanpaHarga"].margin)
        self.assertEqual(by["Habis"].stock_state, "empty")
        self.assertEqual(by["Menipis"].stock_state, "low")
        self.assertEqual(by["Aman"].stock_state, "ok")

    def test_non_admin_forbidden(self):
        User.objects.create_user("cr", password="x", role=Role.COURIER)
        self.client.logout()
        self.client.login(username="cr", password="x")
        self.assertEqual(self.client.get("/list").status_code, 403)


class PetTypeConditionTests(TestCase):
    def test_defaults_for_existing_style_products(self):
        p = make_product()
        self.assertEqual((p.pet_type, p.condition), ("SEMUA", "BARU"))

    def test_migration_created_new_categories(self):
        codes = set(Category.objects.values_list("name", flat=True))
        self.assertTrue({"KESEHATAN", "MAINAN", "PERLENGKAPAN"} <= codes)

    def _data(self, **extra):
        cat, _ = Category.objects.get_or_create(name=Category.FOOD)
        return {"category": cat.pk, "name": "Whiskas", "purchase_price": 1000, "selling_price": 2000,
                "stock": 3, "is_active": "true", **extra}

    def test_form_defaults_when_fields_are_missing(self):
        from .form import FormProduct

        form = FormProduct(self._data())
        self.assertTrue(form.is_valid(), form.errors)
        p = form.save()
        self.assertEqual((p.pet_type, p.condition), ("SEMUA", "BARU"))

    def test_form_saves_pet_type_and_condition_and_rejects_unknown(self):
        from .form import FormProduct

        p = FormProduct(self._data(pet_type="KUCING", condition="BEKAS")).save()
        self.assertEqual((p.pet_type, p.condition), ("KUCING", "BEKAS"))
        self.assertFalse(FormProduct(self._data(pet_type="NAGA")).is_valid())

    def test_admin_pages_offer_pet_type_and_condition(self):
        User.objects.create_user("adm", password="x", role=Role.ADMIN)
        self.client.login(username="adm", password="x")
        make_product()
        r = self.client.get("/staff/admin/manage_product/")
        self.assertContains(r, 'name="pet_type"', count=2)  # form tambah + 1 form edit
        self.assertContains(r, 'name="condition"', count=2)
        self.assertContains(r, "Hamster")



class StockMovementTests(TestCase):
    def test_every_mutation_type_has_a_movement(self):
        from product.models import MOVEMENT_REGISTRY

        self.assertEqual(set(MOVEMENT_REGISTRY), set(MutationType.values))

    def test_stock_in_and_out_behave_differently(self):
        from product.models import StockIn, StockOut

        product = make_product(stock=10)
        self.assertEqual(StockIn().apply(product, 4), 14)
        self.assertEqual(StockOut().apply(product, 4), 6)
        with self.assertRaises(InsufficientStock):
            StockOut().apply(product, 11)

    def test_abstract_movement_cannot_be_instantiated(self):
        from product.models import StockMovement

        with self.assertRaises(TypeError):
            StockMovement()

    def test_unknown_mutation_type_is_rejected(self):
        product = make_product(stock=10)
        with self.assertRaises(ValueError):
            product.apply_mutation("LAINNYA", 1)
