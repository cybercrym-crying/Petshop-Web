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
            {"product": self.p.pk, "mutationType": "IN", "quantity": 4, "note": "restock"},
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 9)
        self.assertContains(self.client.get("/list"), "restock")

    def test_out_over_stock_shows_error_and_keeps_stock(self):
        r = self.client.post(
            "/stock-mutation",
            {"product": self.p.pk, "mutationType": "OUT", "quantity": 99, "note": ""},
        )
        self.assertEqual(r.status_code, 200)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)

    def test_zero_quantity_rejected(self):
        self.client.post(
            "/stock-mutation",
            {"product": self.p.pk, "mutationType": "IN", "quantity": 0, "note": ""},
        )
        self.assertEqual(StockMutation.objects.count(), 0)

    def test_set_price_page_saves(self):
        self.client.post(f"/{self.p.pk}/price", {"selling_price": 20000})
        self.p.refresh_from_db()
        self.assertEqual(self.p.selling_price, 20000)
