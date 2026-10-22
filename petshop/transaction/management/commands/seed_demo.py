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
from courier.models import CourierProfile, CourierStatus
from service.models import Service, ServiceBooking
from product.models import (
    Category,
    MutationType,
    PetType,
    Product,
    ProductCondition,
    StockMutation,
)
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

CASHIERS = [
    ("demo_kasir", "Sari", "Puspita", "081200000021"),
]

GROOMERS = [
    ("demo_groomer1", "Gilang", "Saputra", "081200000031"),
    ("demo_groomer2", "Mega", "Anggraini", "081200000032"),
]

# Akun customer demo yang bisa login ke situs untuk mencoba booking layanan.
DEMO_CUSTOMER = ("demo_customer", "Ayu", "Pratiwi", "081300000099", "Jl. Melur No. 5, Kel. Sungai Pinang")

PET_NAMES = [
    ("Mochi", PetType.CAT), ("Kopi", PetType.DOG), ("Luna", PetType.CAT),
    ("Bruno", PetType.DOG), ("Snowy", PetType.RABBIT), ("Oyen", PetType.CAT),
    ("Max", PetType.DOG), ("Cimol", PetType.CAT),
]

COURIER_PROFILES = {
    "demo_kurir1": ("Honda Beat", "B 4521 KJA", "Area Pusat Kota", CourierStatus.ACTIVE),
    "demo_kurir2": ("Yamaha Mio", "B 7788 TRS", "Area Utara", CourierStatus.ACTIVE),
    "demo_kurir3": (
        "Suzuki Address",
        "B 3092 PLM",
        "Area Selatan",
        CourierStatus.BREAK,
    ),
}

CUSTOMERS = [
    (
        "Siti Aminah",
        "081300000001",
        "Jl. Mawar No. 12, RT 03/RW 01, Kel. Sukamaju, Kec. Mekarsari",
    ),
    (
        "Dewi Kartika",
        "081300000002",
        "Jl. Melati No. 7, Perumahan Griya Asri Blok C2, Kel. Harapan Baru",
    ),
    (
        "Agus Setiawan",
        "081300000003",
        "Jl. Kenanga No. 45, RT 05/RW 02, Kel. Sidomulyo, Kec. Tegalrejo",
    ),
    (
        "Maya Putri",
        "081300000004",
        "Jl. Anggrek No. 3, Komplek Bumi Indah, Kel. Cempaka Putih",
    ),
    (
        "Rizky Ramadhan",
        "081300000005",
        "Jl. Cempaka No. 21, Kel. Sukamaju, Kec. Mekarsari",
    ),
    (
        "Lestari Wulandari",
        "081300000006",
        "Jl. Dahlia No. 9, RT 01/RW 04, Kel. Karang Anyar",
    ),
    (
        "Hendra Gunawan",
        "081300000007",
        "Jl. Flamboyan No. 30, Perumahan Taman Sari, Kel. Tamansari",
    ),
    (
        "Nadia Safitri",
        "081300000008",
        "Jl. Kamboja No. 16, Kel. Baru Tengah, Kec. Baru",
    ),
    ("Fajar Nugroho", "081300000009", "Jl. Teratai No. 2, RT 07/RW 03, Kel. Mulyorejo"),
    (
        "Ayu Lestari",
        "081300000010",
        "Jl. Seruni No. 11, Komplek Griya Permai, Kel. Pondok Indah",
    ),
    (
        "Bambang Hartono",
        "081300000011",
        "Jl. Pahlawan No. 88, RT 02/RW 06, Kel. Gunung Sari",
    ),
    (
        "Putri Handayani",
        "081300000012",
        "Jl. Diponegoro No. 54, Kel. Sumber Rejo, Kec. Tanjung",
    ),
    (
        "Yusuf Maulana",
        "081300000013",
        "Jl. Merdeka No. 17, RT 04/RW 01, Kel. Pasar Baru",
    ),
    (
        "Intan Permatasari",
        "081300000014",
        "Jl. Gajah Mada No. 6, Perumahan Citra Garden, Kel. Mekar Jaya",
    ),
    (
        "Taufik Hidayat",
        "081300000015",
        "Jl. Sudirman No. 102, Kel. Karang Mulya, Kec. Kota",
    ),
    ("Rahmawati", "081300000016", "Jl. Veteran No. 33, RT 06/RW 05, Kel. Sungai Bahau"),
]

M = Category.FOOD
P = Category.EQUIPMENT
A = Category.ACCESSORIES
K = Category.HEALTHCARE
N = Category.TOYS

PHOTO_FOOD = "customer/img/pet-food.png"
PHOTO_TOYS = "customer/img/pet-toys.png"
PHOTO_MEDICINE = "customer/img/pet-drug.png"
PHOTO_ACCESSORIES = "customer/img/pet-accessories.png"

PRODUCTS = [
    (
        "Royal Canin Kitten 400g",
        M,
        78000,
        92000,
        24,
        PHOTO_FOOD,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Whiskas Pouch Tuna 85g",
        M,
        7500,
        10000,
        60,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Whiskas Junior Ocean Fish 1,1kg",
        M,
        52000,
        64000,
        20,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Me-O Tuna Dewasa 1,2kg",
        M,
        38000,
        47000,
        9,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Friskies Seafood 1kg",
        M,
        33000,
        41000,
        30,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Bolt Tuna Kaleng 400g",
        M,
        14000,
        19000,
        40,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Pedigree Adult Beef 1,5kg",
        M,
        62000,
        75000,
        18,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Pro Plan Puppy 1kg",
        M,
        120000,
        145000,
        12,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Makanan Ikan Hias 100g",
        M,
        8000,
        12000,
        40,
        None,
        True,
        PetType.FISH,
        ProductCondition.NEW,
    ),
    (
        "Pelet Ikan Koi 500g",
        M,
        28000,
        38000,
        15,
        None,
        True,
        PetType.FISH,
        ProductCondition.NEW,
    ),
    (
        "Biji-bijian Burung Kenari 500g",
        M,
        18000,
        26000,
        22,
        None,
        True,
        PetType.BIRD,
        ProductCondition.NEW,
    ),
    (
        "Pakan Kelinci Pelet Alfalfa 1kg",
        M,
        30000,
        42000,
        16,
        None,
        True,
        PetType.RABBIT,
        ProductCondition.NEW,
    ),
    (
        "Makanan Hamster Campur 250g",
        M,
        12000,
        18000,
        28,
        None,
        True,
        PetType.HAMSTER,
        ProductCondition.NEW,
    ),
    (
        "Mangkuk Makan Anti-Tumpah",
        P,
        25000,
        38000,
        22,
        PHOTO_FOOD,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Tempat Pasir Kucing + Sekop",
        P,
        55000,
        79000,
        8,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Pasir Kucing Gumpal 5L",
        P,
        42000,
        55000,
        0,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Kandang Travel Kecil",
        P,
        180000,
        None,
        6,
        None,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Kandang Hamster 2 Tingkat",
        P,
        95000,
        135000,
        7,
        None,
        True,
        PetType.HAMSTER,
        ProductCondition.NEW,
    ),
    (
        "Sangkar Burung Kenari",
        P,
        120000,
        165000,
        5,
        None,
        True,
        PetType.BIRD,
        ProductCondition.NEW,
    ),
    (
        "Akuarium Mini 30cm",
        P,
        85000,
        120000,
        10,
        None,
        True,
        PetType.FISH,
        ProductCondition.NEW,
    ),
    (
        "Kandang Lipat Kelinci",
        P,
        210000,
        289000,
        4,
        None,
        True,
        PetType.RABBIT,
        ProductCondition.NEW,
    ),
    (
        "Kandang Kucing Ukuran Sedang (Bekas)",
        P,
        60000,
        90000,
        1,
        None,
        True,
        PetType.CAT,
        ProductCondition.USED,
    ),
    (
        "Sisir Bulu Hewan",
        P,
        15000,
        25000,
        27,
        None,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Shampo Anti Kutu 250ml",
        P,
        22000,
        35000,
        30,
        None,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Tempat Tidur Hewan Empuk M",
        P,
        70000,
        99000,
        11,
        None,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Botol Minum Otomatis Hamster",
        P,
        12000,
        20000,
        25,
        None,
        True,
        PetType.HAMSTER,
        ProductCondition.NEW,
    ),
    (
        "Kalung Kulit Anjing",
        A,
        35000,
        55000,
        14,
        PHOTO_ACCESSORIES,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Harness Kucing Adjustable",
        A,
        28000,
        45000,
        20,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Tali Tuntun 1,5m",
        A,
        18000,
        30000,
        25,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Kalung Lonceng Kucing",
        A,
        6000,
        12000,
        50,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Baju Anjing Motif Batik",
        A,
        45000,
        70000,
        12,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Hoodie Hewan Kecil",
        A,
        40000,
        65000,
        10,
        None,
        False,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Vitamin Bulu Sehat 60 Tablet",
        K,
        45000,
        65000,
        15,
        PHOTO_MEDICINE,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Obat Cacing Kucing 4 Tablet",
        K,
        18000,
        28000,
        20,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Obat Kutu Tetes Anjing",
        K,
        35000,
        52000,
        9,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Salep Jamur Hewan 15g",
        K,
        20000,
        32000,
        18,
        None,
        True,
        PetType.ALL,
        ProductCondition.NEW,
    ),
    (
        "Suplemen Kalsium Kelinci",
        K,
        25000,
        38000,
        14,
        None,
        True,
        PetType.RABBIT,
        ProductCondition.NEW,
    ),
    (
        "Mainan Kucing Felt",
        N,
        12000,
        20000,
        35,
        PHOTO_TOYS,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Tongkat Bulu Kucing",
        N,
        14000,
        22000,
        30,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Tikus Mainan Catnip",
        N,
        8000,
        14000,
        6,
        None,
        True,
        PetType.CAT,
        ProductCondition.NEW,
    ),
    (
        "Bola Karet Anjing",
        N,
        15000,
        25000,
        24,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Tulang Karet Gigit",
        N,
        20000,
        32000,
        18,
        None,
        True,
        PetType.DOG,
        ProductCondition.NEW,
    ),
    (
        "Roda Putar Hamster",
        N,
        22000,
        35000,
        12,
        None,
        True,
        PetType.HAMSTER,
        ProductCondition.NEW,
    ),
    (
        "Ayunan Burung",
        N,
        9000,
        15000,
        20,
        None,
        True,
        PetType.BIRD,
        ProductCondition.NEW,
    ),
]

PRODUCT_NAMES = [p[0] for p in PRODUCTS]
CUSTOMER_PHONES = [c[1] for c in CUSTOMERS]


class Command(BaseCommand):
    help = "Isi database dengan data contoh berbahasa Indonesia (pengguna, produk, pelanggan, dan order)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--orders", type=int, default=40, help="Jumlah order contoh (default 40)."
        )
        parser.add_argument(
            "--more-orders",
            action="store_true",
            help="Tambah order walau data demo sudah ada.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Hapus data demo lebih dulu, lalu isi ulang.",
        )
        parser.add_argument(
            "--password",
            default="demo12345",
            help="Kata sandi akun demo (default demo12345).",
        )
        parser.add_argument(
            "--seed", type=int, default=42, help="Angka acak agar hasilnya selalu sama."
        )
        parser.add_argument(
            "--no-photos", action="store_true", help="Lewati foto produk."
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Izinkan saat DEBUG=False (jangan di server produksi).",
        )

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
            admins, couriers, cashiers, groomers = self.seed_users(opts["password"])
            self.seed_products(admins[0], opts["no_photos"])
            customers = self.seed_customers(opts["password"])
            made = self.seed_orders(
                admins, couriers, customers, opts["orders"], opts["more_orders"]
            )
            self.seed_bookings(customers, groomers, cashiers[0])
        self.summary(made, opts["password"])

    def reset(self):
        with transaction.atomic():
            demo_users = User.objects.filter(username__startswith=DEMO_PREFIX)
            orders = Order.objects.filter(admin__in=demo_users) | Order.objects.filter(
                customer__phone_number__in=CUSTOMER_PHONES
            )
            ServiceBooking.objects.filter(
                customer__phone_number__in=CUSTOMER_PHONES + [DEMO_CUSTOMER[3]]
            ).delete()
            OrderDetail.objects.filter(transaction__in=orders).delete()
            orders.delete()
            products = Product.objects.filter(name__in=PRODUCT_NAMES)
            StockMutation.objects.filter(product__in=products).delete()
            for p in products:
                if p.photo:
                    p.photo.delete(save=False)
            try:
                products.delete()
            except Exception:
                self.stdout.write(
                    self.style.WARNING(
                        "Sebagian produk demo dipakai order lain, dibiarkan."
                    )
                )
            Customer.objects.filter(
                phone_number__in=CUSTOMER_PHONES, orders__isnull=True
            ).delete()
            Cart.objects.filter(user__in=demo_users).delete()
            demo_users.filter(
                order__isnull=True,
                orders_as_courier__isnull=True,
                orders__isnull=True,
                grooming_jobs__isnull=True,
                service_bookings__isnull=True,
            ).delete()
        self.stdout.write("Data demo lama dihapus.")

    def seed_users(self, password):
        def make(row, role):
            username, first, last, phone = row
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "phone_number": phone,
                    "role": role,
                },
            )
            if created:
                user.set_password(password)
                user.save()
            return user

        admins = [make(r, Role.ADMIN) for r in ADMINS]
        couriers = [make(r, Role.COURIER) for r in COURIERS]
        cashiers = [make(r, Role.CASHIER) for r in CASHIERS]
        groomers = [make(r, Role.GROOMER) for r in GROOMERS]
        for courier in couriers:
            vehicle, plate, area, status = COURIER_PROFILES[courier.username]
            CourierProfile.objects.get_or_create(
                user=courier,
                defaults={
                    "vehicle": vehicle,
                    "plate_number": plate,
                    "service_area": area,
                    "status": status,
                },
            )
        return admins, couriers, cashiers, groomers

    def seed_customers(self, password):
        out = []
        for name, phone, address in CUSTOMERS:
            cust, _ = Customer.objects.get_or_create(
                phone_number=phone, defaults={"name": name, "address": address}
            )
            out.append(cust)
        username, first, last, phone, address = DEMO_CUSTOMER
        demo, created = Customer.objects.get_or_create(
            phone_number=phone,
            defaults={
                "username": username,
                "first_name": first,
                "last_name": last,
                "address": address,
            },
        )
        if created:
            demo.set_password(password)
            demo.save()
        out.append(demo)
        return out

    def seed_bookings(self, customers, groomers, cashier, count=14):
        if ServiceBooking.objects.filter(customer__in=customers).exists():
            self.stdout.write("Booking layanan demo sudah ada, dilewati.")
            return
        services = list(Service.objects.active())
        if not services or not groomers:
            return
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        for i in range(count):
            pet_name, pet_type = self.rng.choice(PET_NAMES)
            options = [s for s in services if s.suits(pet_type)] or services
            status = ["done", "done", "process", "pending", "pending"][i % 5]
            if status == "done":
                schedule = now - timedelta(days=self.rng.randint(1, 20), hours=self.rng.randint(0, 6))
            elif status == "process":
                schedule = now - timedelta(minutes=30)
            else:
                schedule = now + timedelta(days=self.rng.randint(0, 5), hours=self.rng.randint(1, 6))
            local = timezone.localtime(schedule)
            schedule = local.replace(hour=max(9, min(local.hour, 18)))  # jam buka
            booking = ServiceBooking.book(
                customer=self.rng.choice(customers),
                service=self.rng.choice(options),
                pet_name=pet_name,
                pet_type=pet_type,
                schedule=schedule,
                created_by=cashier,
            )
            groomer = self.rng.choice(groomers)
            if status in ("process", "done"):
                booking.start(groomer)
            if status == "done":
                booking.finish(groomer, note="Bersih, wangi, kuku sudah dipotong.")
                ServiceBooking.objects.filter(pk=booking.pk).update(
                    started_at=schedule, finished_at=schedule + timedelta(hours=1)
                )

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
        now = timezone.now()
        for (
            name,
            cat_name,
            buy,
            sell,
            stock,
            photo,
            active,
            pet_type,
            condition,
        ) in PRODUCTS:
            category, _ = Category.objects.get_or_create(name=cat_name)
            product, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "purchase_price": buy,
                    "selling_price": sell,
                    "is_active": active,
                    "pet_type": pet_type,
                    "condition": condition,
                },
            )
            if created:
                opened = now - timedelta(days=self.rng.randint(35, 60))
                Product.objects.filter(pk=product.pk).update(created_at=opened)
                if stock > 0:
                    mutation = product.apply_mutation(
                        MutationType.IN, stock, user=admin, note="Stok awal"
                    )
                    StockMutation.objects.filter(pk=mutation.pk).update(date=opened)
                else:
                    first = product.apply_mutation(
                        MutationType.IN, 5, user=admin, note="Stok awal"
                    )
                    second = product.apply_mutation(
                        MutationType.OUT, 5, user=admin, note="Terjual habis"
                    )
                    StockMutation.objects.filter(pk=first.pk).update(date=opened)
                    StockMutation.objects.filter(pk=second.pk).update(
                        date=opened + timedelta(days=10)
                    )
            if photo and not no_photos and not product.photo:
                content = self.photo_file(photo)
                if content:
                    product.photo.save(f"demo-{product.pk}.png", content, save=True)

    def seed_orders(self, admins, couriers, customers, count, more):
        if Order.objects.filter(admin__in=admins).exists() and not more:
            self.stdout.write(
                "Order demo sudah ada, dilewati (pakai --more-orders untuk menambah)."
            )
            return 0
        now = timezone.now()
        made = 0
        for _ in range(count):
            admin = self.rng.choice(admins)
            sellable = list(
                Product.objects.sellable().filter(stock__gt=0, name__in=PRODUCT_NAMES)
            )
            if not sellable:
                break
            Cart.objects.filter(user=admin).delete()
            cart = Cart.objects.create(user=admin)
            for product in self.rng.sample(
                sellable, k=min(len(sellable), self.rng.randint(1, 4))
            ):
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
            StockMutation.objects.filter(note__startswith=f"Order #{order.pk}").update(
                date=when
            )
            made += 1
        return made

    def advance(self, order, couriers, now):
        status = self.rng.choices(
            ["confirmed", "on_delivery", "delivered", "cancelled"],
            weights=[20, 12, 55, 13],
        )[0]
        transfer = order.payment_method == PaymentMethod.TRANSFER
        if status == "confirmed":
            if transfer and self.rng.random() < 0.4:
                order.mark_paid()
            # Aturan asli: kurir hanya bisa ditugaskan bila transfer sudah lunas.
            if order.is_ready_to_ship and self.rng.random() < 0.35:
                order.assign_courier(self.rng.choice(couriers))
            return now - timedelta(minutes=self.rng.randint(10, 240))
        if status == "on_delivery":
            if transfer:
                order.mark_paid()  # transfer harus lunas sebelum dikirim
            order.mark_on_delivery(self.rng.choice(couriers))
            return now - timedelta(hours=self.rng.randint(1, 6))
        if status == "delivered":
            if transfer:
                order.mark_paid()  # transfer harus lunas sebelum dikirim
            order.mark_on_delivery(self.rng.choice(couriers))
            order.mark_delivered()
            return now - timedelta(
                days=self.rng.randint(1, 28), hours=self.rng.randint(0, 8)
            )
        if transfer and self.rng.random() < 0.3:
            order.mark_paid()
        order.cancel()
        return now - timedelta(
            days=self.rng.randint(1, 20), hours=self.rng.randint(0, 8)
        )

    def summary(self, made, password):
        self.stdout.write(self.style.SUCCESS("Data demo siap."))
        self.stdout.write(
            f"  Produk      : {Product.objects.filter(name__in=PRODUCT_NAMES).count()}\n"
            f"  Pelanggan   : {Customer.objects.filter(phone_number__in=CUSTOMER_PHONES).count()}\n"
            f"  Order       : +{made} (total {Order.objects.count()})\n"
            f"  Login admin : demo_admin / {password}\n"
            f"  Login kurir : demo_kurir1 / {password}\n"
            f"  Login kasir : demo_kasir / {password}\n"
            f"  Login groomer: demo_groomer1 / {password}\n"
            f"  Login customer: demo_customer / {password}\n"
            f"  Booking     : {ServiceBooking.objects.count()}"
        )
