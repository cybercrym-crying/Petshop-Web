"""Isi database dengan data contoh (demo) supaya semua halaman punya isi.

    python manage.py seed_demo                 # data dasar + 30 order contoh
    python manage.py seed_demo --orders 60     # lebih banyak order
    python manage.py seed_demo --reset         # hapus data demo lalu isi ulang

Aman dijalankan berulang: user, customer, dan produk tidak digandakan, dan order hanya
dibuat kalau belum ada (pakai --more-orders untuk menambah). Semua data demo bisa
dikenali: username berawalan `demo_`, nomor customer 0813-0000-00xx, dan produk dari daftar di
bawah. Data milikmu sendiri tidak disentuh.
"""

import io
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image

from account.models import Customer, Role, User
from product.models import Category, MutationType, Product, StockMutation
from transaction.models import (
    Cart,
    CartItem,
    Order,
    OrderDetail,
    PaymentMethod,
)

DEMO_PREFIX = "demo_"

ADMINS = [
    ("demo_admin", "Rina", "Wulandari", "081200000001"),
    ("demo_admin2", "Doni", "Prakoso", "081200000002"),
]
COURIERS = [
    ("demo_kurir1", "Budi", "Santoso", "081200000011"),
    ("demo_kurir2", "Citra", "Lestari", "081200000012"),
    ("demo_kurir3", "Eko", "Wijaya", "081200000013"),
]
CUSTOMERS = [
    ("Siti Aminah", "081300000001", "Jl. Mawar No. 12, RT 03, Kec. Contoh"),
    ("Dewi Kartika", "081300000002", "Jl. Melati No. 7, Perum Griya Asri Blok C2"),
    ("Agus Setiawan", "081300000003", "Jl. Kenanga No. 45, RT 05 RW 02"),
    ("Maya Putri", "081300000004", "Jl. Anggrek No. 3, Kompleks Bumi Indah"),
    ("Rizky Ramadhan", "081300000005", "Jl. Cempaka No. 21, Kel. Sukamaju"),
    ("Lestari Wulan", "081300000006", "Jl. Dahlia No. 9, RT 01 RW 04"),
    ("Hendra Gunawan", "081300000007", "Jl. Flamboyan No. 30, Perum Taman Sari"),
    ("Nadia Safitri", "081300000008", "Jl. Kamboja No. 16, Kec. Contoh Baru"),
    ("Fajar Nugroho", "081300000009", "Jl. Teratai No. 2, RT 07 RW 03"),
    ("Ayu Lestari", "081300000010", "Jl. Seruni No. 11, Kompleks Griya Permai"),
]
# (nama, kategori, harga beli, harga jual atau None, stok awal, foto, aktif)
PRODUCTS = [
    ("Royal Canin Kitten 400g", Category.FOOD, 78000, 92000, 24, None, True),
    ("Whiskas Pouch Tuna 85g", Category.FOOD, 7500, 10000, 60, None, True),
    ("Pedigree Adult Beef 1.5kg", Category.FOOD, 62000, 75000, 18, None, True),
    ("Me-O Tuna Dewasa 1.2kg", Category.FOOD, 38000, 47000, 9, None, True),  # menipis
    ("Pro Plan Puppy 1kg", Category.FOOD, 120000, 145000, 12, None, True),
    ("Friskies Seafood 1kg", Category.FOOD, 33000, 41000, 30, None, True),
    ("Makanan Ikan Hias 100g", Category.FOOD, 8000, 12000, 40, None, True),
    ("Mangkuk Makan Anti-Tumpah", Category.EQUIPMENT, 25000, 38000, 22, "customer/img/pet-food.png", True),
    ("Mainan Kucing Felt", Category.EQUIPMENT, 12000, 20000, 35, "customer/img/pet-toys.png", True),
    ("Tempat Pasir Kucing + Sekop", Category.EQUIPMENT, 55000, 79000, 8, None, True),  # menipis
    ("Sisir Bulu Hewan", Category.EQUIPMENT, 15000, 25000, 27, None, True),
    ("Vitamin Bulu Sehat 60 Tablet", Category.EQUIPMENT, 45000, 65000, 15, "customer/img/pet-drug.png", True),
    ("Pasir Kucing Gumpal 5L", Category.EQUIPMENT, 42000, 55000, 0, None, True),  # habis
    ("Kandang Travel Kecil", Category.EQUIPMENT, 180000, None, 6, None, True),  # harga belum diset
    ("Kalung Kulit Anjing", Category.ACCESSORIES, 35000, 55000, 14, "customer/img/pet-accessories.png", True),
    ("Harness Kucing Adjustable", Category.ACCESSORIES, 28000, 45000, 20, None, True),
    ("Tali Tuntun 1.5m", Category.ACCESSORIES, 18000, 30000, 25, None, True),
    ("Hoodie Hewan Kecil", Category.ACCESSORIES, 40000, 65000, 10, None, False),  # nonaktif
]
PRODUCT_NAMES = [p[0] for p in PRODUCTS]
CUSTOMER_PHONES = [c[1] for c in CUSTOMERS]


class Command(BaseCommand):
    help = "Isi database dengan data contoh (user, produk, customer, dan order)."

    def add_arguments(self, parser):
        parser.add_argument("--orders", type=int, default=30, help="Jumlah order contoh (default 30).")
        parser.add_argument("--more-orders", action="store_true", help="Tambah order walau data demo sudah ada.")
        parser.add_argument("--reset", action="store_true", help="Hapus data demo lebih dulu, lalu isi ulang.")
        parser.add_argument("--password", default="demo12345", help="Password akun demo (default demo12345).")
        parser.add_argument("--seed", type=int, default=42, help="Angka acak agar hasilnya sama tiap kali.")
        parser.add_argument("--no-photos", action="store_true", help="Lewati foto produk.")
        parser.add_argument("--force", action="store_true", help="Izinkan saat DEBUG=False (jangan di server produksi).")

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError(
                "DEBUG=False: ini terlihat seperti server produksi. Data demo tidak diisi. "
                "Pakai --force kalau memang disengaja."
            )
        self.rng = random.Random(opts["seed"])
        if opts["reset"]:
            self.reset()
        with transaction.atomic():
            admins, couriers = self.seed_users(opts["password"])
            self.seed_products(admins[0], opts["no_photos"])
            customers = self.seed_customers()
            made = self.seed_orders(admins, couriers, customers, opts["orders"], opts["more_orders"])
        self.summary(made, opts["password"])

    # ---------- reset ----------
    def reset(self):
        with transaction.atomic():
            demo_users = User.objects.filter(username__startswith=DEMO_PREFIX)
            orders = Order.objects.filter(admin__in=demo_users) | Order.objects.filter(
                customer__phone_number__in=CUSTOMER_PHONES
            )
            OrderDetail.objects.filter(transaction__in=orders).delete()
            orders.delete()
            products = Product.objects.filter(name__in=PRODUCT_NAMES)
            StockMutation.objects.filter(product__in=products).delete()
            for p in products:
                if p.photo:
                    p.photo.delete(save=False)
            try:
                products.delete()
            except Exception:  # produk milik data lain yang masih dipakai order non-demo
                self.stdout.write(self.style.WARNING("Sebagian produk demo dipakai order lain, dibiarkan."))
            Customer.objects.filter(phone_number__in=CUSTOMER_PHONES, orders__isnull=True).delete()
            Cart.objects.filter(user__in=demo_users).delete()
            demo_users.filter(order__isnull=True, orders_as_courier__isnull=True).delete()
        self.stdout.write("Data demo lama dihapus.")

    # ---------- data dasar ----------
    def seed_users(self, password):
        def make(row, role):
            username, first, last, phone = row
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "phone_number": phone, "role": role},
            )
            if created:
                user.set_password(password)
                user.save()
            return user

        return [make(r, Role.ADMIN) for r in ADMINS], [make(r, Role.COURIER) for r in COURIERS]

    def seed_customers(self):
        out = []
        for name, phone, address in CUSTOMERS:
            cust, _ = Customer.objects.get_or_create(
                phone_number=phone, defaults={"name": name, "address": address}
            )
            out.append(cust)
        return out

    def photo_file(self, static_path):
        found = finders.find(static_path)
        if not found:
            return None
        img = Image.open(found)
        img.thumbnail((600, 600))
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return ContentFile(buf.getvalue())

    def seed_products(self, admin, no_photos):
        for name, cat_name, buy, sell, stock, photo, active in PRODUCTS:
            category, _ = Category.objects.get_or_create(name=cat_name)
            product, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "purchase_price": buy,
                    "selling_price": sell,
                    "is_active": active,
                },
            )
            if created and stock > 0:
                # Stok masuk lewat apply_mutation supaya riwayat stok ikut tercatat.
                product.apply_mutation(
                    MutationType.IN, stock, user=admin, note="Stok awal (data demo)"
                )
            if created and stock == 0:
                product.apply_mutation(MutationType.IN, 5, user=admin, note="Stok awal (data demo)")
                product.apply_mutation(MutationType.OUT, 5, user=admin, note="Terjual habis (data demo)")
            if photo and not no_photos and not product.photo:
                content = self.photo_file(photo)
                if content:
                    product.photo.save(f"demo-{product.pk}.png", content, save=True)

    # ---------- order ----------
    def seed_orders(self, admins, couriers, customers, count, more):
        if Order.objects.filter(admin__in=admins).exists() and not more:
            self.stdout.write("Order demo sudah ada, dilewati (pakai --more-orders untuk menambah).")
            return 0
        now = timezone.now()
        made = 0
        for _ in range(count):
            admin = self.rng.choice(admins)
            sellable = list(Product.objects.sellable().filter(stock__gt=0, name__in=PRODUCT_NAMES))
            if not sellable:
                break
            Cart.objects.filter(user=admin).delete()
            cart = Cart.objects.create(user=admin)
            for product in self.rng.sample(sellable, k=min(len(sellable), self.rng.randint(1, 4))):
                qty = self.rng.randint(1, min(3, product.stock))
                CartItem.objects.create(cart=cart, product=product, quantity=qty)
            method = self.rng.choices(
                [PaymentMethod.TRANSFER, PaymentMethod.CASH], weights=[65, 35]
            )[0]
            order = cart.checkout(
                customer=self.rng.choice(customers), admin=admin, payment_method=method
            )
            when = self.advance(order, couriers, now)
            Order.objects.filter(pk=order.pk).update(date=when)
            made += 1
        return made

    def advance(self, order, couriers, now):
        """Geser order ke status acak dan kembalikan waktu pembuatannya."""
        status = self.rng.choices(
            ["confirmed", "on_delivery", "delivered", "cancelled"], weights=[25, 15, 45, 15]
        )[0]
        transfer = order.payment_method == PaymentMethod.TRANSFER
        if status == "confirmed":
            if transfer and self.rng.random() < 0.4:
                order.mark_paid()
            if self.rng.random() < 0.35:
                order.courier = self.rng.choice(couriers)
                order.save(update_fields=["courier"])
            return now - timedelta(minutes=self.rng.randint(10, 240))
        if status == "on_delivery":
            if transfer and self.rng.random() < 0.85:
                order.mark_paid()
            order.mark_on_delivery(self.rng.choice(couriers))
            return now - timedelta(hours=self.rng.randint(1, 6))
        if status == "delivered":
            order.mark_on_delivery(self.rng.choice(couriers))
            order.mark_delivered()
            if transfer:
                order.mark_paid()
            return now - timedelta(days=self.rng.randint(1, 13), hours=self.rng.randint(0, 8))
        if transfer and self.rng.random() < 0.3:
            order.mark_paid()
        order.cancel()
        return now - timedelta(days=self.rng.randint(1, 10), hours=self.rng.randint(0, 8))

    def summary(self, made, password):
        self.stdout.write(self.style.SUCCESS("Data demo siap."))
        self.stdout.write(
            f"  Produk   : {Product.objects.filter(name__in=PRODUCT_NAMES).count()}\n"
            f"  Customer : {Customer.objects.filter(phone_number__in=CUSTOMER_PHONES).count()}\n"
            f"  Order    : +{made} (total {Order.objects.count()})\n"
            f"  Login admin : demo_admin / {password}\n"
            f"  Login kurir : demo_kurir1 / {password}"
        )
