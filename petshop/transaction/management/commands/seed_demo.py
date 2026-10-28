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

from account.models import Approval, Customer, Role, User
from courier.models import CashRemittance, CourierLocation, CourierProfile, CourierStatus
from service.models import BookingStatus, BookingStep, Pet, Service, ServiceBooking
from store.models import ActivityLog, BankAccount, Complaint, ComplaintStatus, Notification, StoreSettings
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

from . import _demo_images as media
from ._demo_text import (
    BOOKING_NOTES,
    GROOMER_NOTES,
    MORE_CUSTOMERS,
    ORDER_NOTES,
    PET_NAMES_MORE,
    PRODUCT_DESCRIPTIONS,
)

DEMO_PREFIX = "demo_"

SUPERADMINS = [
    ("demo_superadmin", "Hendra", "Kusuma", "081200000000"),
]

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

# Pendaftar staf yang belum disetujui (tab "Persetujuan Staf" di Kelola Akun).
PENDING_STAFF = [
    ("demo_calon_kurir", "Fajar", "Ramadhan", "081200000041", Role.COURIER, ("Yamaha NMAX", "KT 4411 FR", True)),
    ("demo_calon_kurir2", "Intan", "Permata", "081200000042", Role.COURIER, ("Honda Vario", "KT 5520 IP", False)),
]

# Rekening contoh; ganti dengan rekening asli di Pengaturan Toko.
DEMO_BANKS = [
    ("BCA", "0000000001", "Seelly Petshop (contoh)"),
    ("Mandiri", "0000000002", "Seelly Petshop (contoh)"),
]

# Akun customer demo yang bisa login ke situs untuk mencoba booking layanan.
DEMO_CUSTOMER = ("demo_customer", "Ayu", "Pratiwi", "081300000099", "Jl. Melur No. 5, Kel. Sungai Pinang Dalam, Samarinda")

# Akun pelanggan yang masing-masing fokus pada satu fitur (data lengkap ada di demo_customer).
FEATURE_CUSTOMERS = [
    ("demo_belanja", "Rudi", "Hartanto", "081300000101", "Jl. Pramuka No. 21, Kel. Gunung Kelua, Samarinda"),
    ("demo_grooming", "Nisa", "Rahmadani", "081300000102", "Jl. Wahid Hasyim II No. 14, Kel. Sempaja Selatan, Samarinda"),
    ("demo_komplain", "Bayu", "Saputra", "081300000103", "Jl. Pangeran Suryanata No. 9, Kel. Bukit Pinang, Samarinda"),
]
ACCOUNT_PHONES = [DEMO_CUSTOMER[3]] + [row[3] for row in FEATURE_CUSTOMERS]

# Alamat & titik toko demo. Titik peta perkiraan; geser di Pengaturan Toko bila perlu.
STORE_ADDRESS = "Jl. Ery Suparjan No. 02, Samarinda, Kalimantan Timur"
STORE_POINT = ("-0.483900", "117.141600")

PET_NAMES = [
    ("Mochi", PetType.CAT), ("Kopi", PetType.DOG), ("Luna", PetType.CAT),
    ("Bruno", PetType.DOG), ("Snowy", PetType.RABBIT), ("Oyen", PetType.CAT),
    ("Max", PetType.DOG), ("Cimol", PetType.CAT),
]

COURIER_PROFILES = {
    "demo_kurir1": ("Honda Beat", "KT 4521 KJ", "Samarinda Ulu & Kota", CourierStatus.ACTIVE),
    "demo_kurir2": ("Yamaha Mio", "KT 7788 TR", "Samarinda Utara & Sungai Pinang", CourierStatus.ACTIVE),
    "demo_kurir3": (
        "Suzuki Address",
        "KT 3092 PL",
        "Sungai Kunjang & Seberang",
        CourierStatus.BREAK,
    ),
}

CUSTOMERS = [
    (
        "Siti Aminah",
        "081300000001",
        "Jl. Juanda No. 12, RT 03, Kel. Air Hitam, Kec. Samarinda Ulu",
    ),
    (
        "Dewi Kartika",
        "081300000002",
        "Jl. M. Yamin No. 7, Perumahan Griya Asri Blok C2, Kel. Gunung Kelua",
    ),
    (
        "Agus Setiawan",
        "081300000003",
        "Jl. Siradj Salman No. 45, RT 05, Kel. Air Putih, Kec. Samarinda Ulu",
    ),
    (
        "Maya Putri",
        "081300000004",
        "Jl. Pemuda No. 3, Kel. Temindung Permai, Kec. Sungai Pinang",
    ),
    (
        "Rizky Ramadhan",
        "081300000005",
        "Jl. Dr. Soetomo No. 21, Kel. Sidodadi, Kec. Samarinda Ulu",
    ),
    (
        "Lestari Wulandari",
        "081300000006",
        "Jl. Antasari No. 9, RT 01, Kel. Teluk Lerong Ulu",
    ),
    (
        "Hendra Gunawan",
        "081300000007",
        "Jl. Pahlawan No. 30, Kel. Dadi Mulya, Kec. Samarinda Ulu",
    ),
    (
        "Nadia Safitri",
        "081300000008",
        "Jl. Kadrie Oening No. 16, Kel. Air Hitam, Kec. Samarinda Ulu",
    ),
    ("Fajar Nugroho", "081300000009", "Jl. AW Syahranie No. 2, RT 07, Kel. Air Hitam"),
    (
        "Ayu Lestari",
        "081300000010",
        "Jl. Agus Salim No. 11, Kel. Sungai Pinang Luar, Kec. Samarinda Kota",
    ),
    (
        "Bambang Hartono",
        "081300000011",
        "Jl. Lambung Mangkurat No. 88, Kel. Pelita, Kec. Samarinda Ilir",
    ),
    (
        "Putri Handayani",
        "081300000012",
        "Jl. Cendana No. 54, Kel. Teluk Lerong Ilir, Kec. Samarinda Ulu",
    ),
    (
        "Yusuf Maulana",
        "081300000013",
        "Jl. Merdeka No. 17, RT 04, Kel. Sungai Pinang Dalam",
    ),
    (
        "Intan Permatasari",
        "081300000014",
        "Jl. Gerilya No. 6, Perumahan Citra Garden, Kel. Sungai Pinang Dalam",
    ),
    (
        "Taufik Hidayat",
        "081300000015",
        "Jl. Slamet Riyadi No. 102, Kel. Karang Asam Ilir, Kec. Sungai Kunjang",
    ),
    ("Rahmawati", "081300000016", "Jl. KH Mas Mansyur No. 33, RT 06, Kel. Karang Asam Ulu"),
]

M = Category.FOOD
P = Category.EQUIPMENT
A = Category.ACCESSORIES
K = Category.HEALTHCARE
N = Category.TOYS

PHOTO_TOYS = "customer/img/category-toys.jpg"

# Foto produk: demo_assets/products/<slug nama>.jpg (foto kemasan kiriman pemilik toko;
# mainan memakai gambar kemasan buatan sendiri). Kolom: nama, kategori, harga beli,
# harga jual, stok awal (0 = sengaja habis), foto cadangan, aktif, jenis hewan, kondisi.
PRODUCTS = [
    ("Bolt Tuna Mother & Kitten Kaleng 400g", M, 15500, 21000, 30, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Salmon Kaleng 400g", M, 14500, 19500, 28, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Tuna Kaleng 400g", M, 14500, 19500, 36, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Tuna & Sardines Kaleng 400g", M, 14500, 19500, 24, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Mixed Fish Platter Kaleng 400g", M, 14500, 19500, 7, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Plus Tuna & Chicken 5kg", M, 118000, 145000, 9, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Tuna Kibble Ikan 20kg", M, 335000, 395000, 4, None, True, PetType.CAT, ProductCondition.NEW),
    ("Bolt Dog Puppy 800g", M, 24000, 31000, 22, None, True, PetType.DOG, ProductCondition.NEW),
    ("Bolt Dog Small Breed Adult 20kg", M, 395000, 460000, 3, None, True, PetType.DOG, ProductCondition.NEW),
    ("Bolt Dog Lamb Kibble Bulat 20kg", M, 360000, 420000, 3, None, True, PetType.DOG, ProductCondition.NEW),
    ("Bolt Dog Beef Kibble Segitiga 20kg", M, 360000, 420000, 0, None, True, PetType.DOG, ProductCondition.NEW),
    ("Takari Koki Sinking 100g", M, 11000, 15000, 26, None, True, PetType.FISH, ProductCondition.NEW),
    ("Takari Mix 100g", M, 9500, 13000, 30, None, True, PetType.FISH, ProductCondition.NEW),
    ("Takari Red 100g", M, 9500, 13000, 32, None, True, PetType.FISH, ProductCondition.NEW),
    ("Takari Green 100g", M, 9500, 13000, 18, None, True, PetType.FISH, ProductCondition.NEW),
    ("Pakan Ikan Koi PK 2mm 10kg", M, 205000, 245000, 5, None, True, PetType.FISH, ProductCondition.NEW),
    ("Pakan Ikan Koi PK 5mm 10kg", M, 205000, 245000, 4, None, True, PetType.FISH, ProductCondition.NEW),
    ("Pakan Ikan Koi Spesial 10kg", M, 240000, 285000, 3, None, True, PetType.FISH, ProductCondition.NEW),
    ("Pakan Koi Super Red 10kg", M, 265000, 315000, 2, None, True, PetType.FISH, ProductCondition.NEW),
    ("Tory Daily Pakan Burung Dewasa 100g", M, 14000, 19000, 20, None, True, PetType.BIRD, ProductCondition.NEW),
    ("Tory Junior Pakan Anakan Burung 100g", M, 15500, 21000, 14, None, True, PetType.BIRD, ProductCondition.NEW),
    ("Tory Fighter Pakan Burung Kontes 100g", M, 17000, 23000, 12, None, True, PetType.BIRD, ProductCondition.NEW),
    ("C.P. Singing Bird Food", M, 9000, 12500, 25, None, True, PetType.BIRD, ProductCondition.NEW),
    ("Classic Singing Bird Food Seaweed 400g", M, 22000, 28000, 16, None, True, PetType.BIRD, ProductCondition.NEW),
    ("Classic Singing Bird Food Anti Stress 400g", M, 22000, 28000, 15, None, True, PetType.BIRD, ProductCondition.NEW),
    ("Nice Makanan Kelinci Dewasa 1kg", M, 26000, 34000, 18, None, True, PetType.RABBIT, ProductCondition.NEW),
    ("Hamutaro Rainbow Premium Hamster Food", M, 17000, 24000, 21, None, True, PetType.HAMSTER, ProductCondition.NEW),
    ("BentoCat Premium Clumping Litter 10L", P, 58000, 75000, 19, None, True, PetType.CAT, ProductCondition.NEW),
    ("Kandang Kucing Sweet Cage Size L (Bekas)", P, 220000, 300000, 1, None, True, PetType.CAT, ProductCondition.USED),
    ("Baju Kucing Batik Nusantara", A, 32000, 45000, 14, None, True, PetType.CAT, ProductCondition.NEW),
    ("Tali Tuntun Anjing Tambang Thomas", A, 85000, 115000, 6, None, True, PetType.DOG, ProductCondition.NEW),
    ("Diarril Kelinci Kapsul", K, 11000, 16000, 15, None, True, PetType.RABBIT, ProductCondition.NEW),
    ("Ketwol Drops 15ml", K, 19000, 26000, 12, None, True, PetType.CAT, ProductCondition.NEW),
    ("Pussycap Kapsul Vitamin Kucing", K, 11000, 16000, 20, None, True, PetType.CAT, ProductCondition.NEW),
    ("Rabbittoxy Stop Pilek Kelinci", K, 11000, 16000, 10, None, True, PetType.RABBIT, ProductCondition.NEW),
    ("Terafit 10 Kapsul Obat Burung", K, 9000, 14000, 17, None, True, PetType.BIRD, ProductCondition.NEW),
    ("Whiscat Shampoo Kucing", K, 21000, 29000, 13, None, True, PetType.CAT, ProductCondition.NEW),
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
        "Roda Putar Hamster",  # barang baru datang, harga jual belum ditetapkan admin
        N,
        22000,
        None,
        12,
        None,
        True,
        PetType.HAMSTER,
        ProductCondition.NEW,
    ),
    (
        "Ayunan Burung",  # sudah tidak dijual (nonaktif), tetap tercatat di riwayat
        N,
        9000,
        15000,
        20,
        None,
        False,
        PetType.BIRD,
        ProductCondition.NEW,
    ),
]

CUSTOMERS = CUSTOMERS + MORE_CUSTOMERS
PET_NAMES = PET_NAMES + PET_NAMES_MORE
HISTORY_DAYS = 90  # order & booking tersebar 90 hari ke belakang (cocok dgn dasbor)

PRODUCT_NAMES = [p[0] for p in PRODUCTS]
SOLD_OUT = [p[0] for p in PRODUCTS if p[4] == 0]  # sengaja habis, tidak direstok
CUSTOMER_PHONES = [c[1] for c in CUSTOMERS]


def demo_email(name):
    return ".".join(name.lower().split()) + "@example.com"  # domain contoh, bukan email asli


class Command(BaseCommand):
    help = "Isi database dengan data contoh berbahasa Indonesia (pengguna, produk, pelanggan, dan order)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--orders", type=int, default=160, help="Jumlah order contoh (default 160)."
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
            "--media-only",
            action="store_true",
            help="Hanya pulihkan file demo yang hilang (QRIS contoh, foto produk, foto profil, foto hewan); data lain tidak diubah.",
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
        if opts["media_only"]:
            self.restore_media()
            return
        if opts["reset"]:
            self.reset()
        with transaction.atomic():
            admins, couriers, cashiers, groomers = self.seed_users(opts["password"])
            self.seed_store(admins[0])
            self.seed_products(admins[0], opts["no_photos"])
            customers = self.seed_customers(opts["password"])
            made = self.seed_orders(
                admins, couriers, customers, opts["orders"], opts["more_orders"]
            )
            self.seed_bookings(customers, groomers, cashiers[0], no_photos=opts["no_photos"])
            extra = self.seed_feature_accounts(
                opts["password"], admins, couriers, cashiers[0], groomers, customers[-1], opts["no_photos"]
            )
            self.seed_courier_tracks(couriers)
            self.seed_pet_trip(customers)
            self.seed_cod_and_remittances(couriers, cashiers[0])
            self.seed_reviews_and_complaints(customers, cashiers[0])
            self.seed_feature_complaints(extra, cashiers[0])
            self.seed_pos(admins, cashiers[0], customers)
            fresh = list(extra) + ([DEMO_CUSTOMER[0]] if made else [])
            self.seed_customer_notifications(fresh)
            if not opts["no_photos"]:
                self.seed_media()
        self.summary(made, opts["password"])

    def reset(self):
        with transaction.atomic():
            demo_users = User.objects.filter(username__startswith=DEMO_PREFIX)
            orders = Order.objects.filter(admin__in=demo_users) | Order.objects.filter(
                customer__phone_number__in=CUSTOMER_PHONES + ACCOUNT_PHONES
            )
            from transaction.models import CashierShift, OrderServiceLine, ReturnRequest

            ReturnRequest.objects.filter(order__in=orders).delete()
            OrderServiceLine.objects.filter(order__in=orders).delete()
            Complaint.objects.filter(
                customer__phone_number__in=CUSTOMER_PHONES + ACCOUNT_PHONES
            ).delete()
            ServiceBooking.objects.filter(
                customer__phone_number__in=CUSTOMER_PHONES + ACCOUNT_PHONES
            ).delete()
            OrderDetail.objects.filter(transaction__in=orders).delete()
            orders.delete()
            CashierShift.objects.filter(cashier__in=demo_users).delete()
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
            Notification.objects.filter(user__in=demo_users).delete()
            CourierLocation.objects.filter(courier__in=demo_users).delete()
            CashRemittance.objects.filter(courier__in=demo_users).delete()
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

        superadmins = [make(r, Role.SUPERADMIN) for r in SUPERADMINS]
        # Super Admin demo juga bisa membuka /admin/ untuk melihat semua tabel.
        User.objects.filter(pk__in=[u.pk for u in superadmins]).update(is_staff=True, is_superuser=True)
        admins = [make(r, Role.ADMIN) for r in ADMINS]
        User.objects.filter(pk__in=[u.pk for u in admins]).update(is_staff=False, is_superuser=False)
        for username, first, last, phone, role, courier in PENDING_STAFF:
            user = make((username, first, last, phone), role)
            User.objects.filter(pk=user.pk).update(approval=Approval.PENDING, is_active=False)
            if courier:
                vehicle, plate, _pets = courier
                CourierProfile.objects.get_or_create(
                    user=user, defaults={"vehicle": vehicle, "plate_number": plate}
                )
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

    def seed_store(self, admin):
        store = StoreSettings.current()
        if not store.updated_by_id:  # jangan menimpa alamat yang sudah diisi admin
            store.address = STORE_ADDRESS
            store.latitude, store.longitude = STORE_POINT
        store.save()
        if not BankAccount.objects.exists():
            for n, (bank, number, holder) in enumerate(DEMO_BANKS):
                BankAccount.objects.create(bank=bank, number=number, holder=holder, order=n)
        if not Notification.objects.filter(user__username__startswith=DEMO_PREFIX).exists():
            Notification.to_staff(
                [Role.SUPERADMIN, Role.ADMIN],
                "Pendaftaran staf baru",
                "Fajar Ramadhan mendaftar sebagai Kurir dan menunggu persetujuan.",
                "/staff/admin/manage_account?tab=approval",
            )

    def seed_customers(self, password):
        out = []
        for name, phone, address in CUSTOMERS:
            cust, _ = Customer.objects.get_or_create(
                phone_number=phone,
                defaults={"name": name, "address": address, "email": demo_email(name)},
            )
            if not cust.email:
                Customer.objects.filter(pk=cust.pk).update(email=demo_email(name))
            out.append(cust)
        username, first, last, phone, address = DEMO_CUSTOMER
        demo, created = Customer.objects.get_or_create(
            phone_number=phone,
            defaults={
                "username": username,
                "first_name": first,
                "last_name": last,
                "address": address,
                "email": "demo.customer@example.com",
            },
        )
        if created:
            demo.set_password(password)
            demo.save()
        out.append(demo)
        return out

    def seed_pets(self, customers):
        """Profil hewan pelanggan (1-2 per pelanggan) dari daftar nama hewan demo."""
        pool = list(dict.fromkeys(PET_NAMES))
        breeds = {"KUCING": ["Persia", "Anggora", "Domestik", "Bengal", "British Shorthair"],
                  "ANJING": ["Golden Retriever", "French Bulldog", "Pomeranian", "Shih Tzu", "Kampung"],
                  "KELINCI": ["Holland Lop", "Lokal"]}
        pets = {}
        for customer in customers:
            mine = list(Pet.objects.filter(owner=customer))
            if not mine:
                rng = random.Random(customer.phone_number)
                picks = [("Mochi", "KUCING"), ("Kopi", "ANJING")] if customer.username == DEMO_CUSTOMER[0] else rng.sample(pool, k=rng.randint(1, 2))
                fixed = {"Mochi": "Persia", "Kopi": "Golden Retriever"} if customer.username == DEMO_CUSTOMER[0] else {}
                for name, pet_type in picks:
                    mine.append(Pet.objects.create(
                        owner=customer, name=name, pet_type=pet_type,
                        breed=fixed.get(name) or rng.choice(breeds.get(pet_type, [""])),
                        sex=rng.choice(["JANTAN", "BETINA"]),
                        birth_date=timezone.localdate() - timedelta(days=rng.randint(200, 2500)),
                        weight_kg=round(rng.uniform(2.5, 4.8) if pet_type != "ANJING" else rng.uniform(3, 18), 1),
                        notes=rng.choice(["", "", "Alergi sampo beraroma kuat.", "Takut suara pengering.", "Kulit sensitif."]),
                    ))
            pets[customer.pk] = mine
        return pets

    def demo_step_photo(self, booking, step_name, when=None):
        """Foto tahap grooming: foto hewan sesuai rasnya dengan cap tahap & jam.
        Ras tanpa foto yang cocok memakai kartu CONTOH (jelas ditandai data demo)."""
        pet = booking.pet
        when = timezone.localtime(when or timezone.now())
        photo = media.pet_photo(
            pet.breed if pet else "", booking.pk + len(step_name),
            stamp=[f"Seelly Grooming · {step_name[:28]}", f"{booking.pet_name} · {when:%d/%m/%Y %H:%M}"],
            name=f"demo-tahap-{booking.pk}.jpg",
        )
        if photo:
            return photo
        from PIL import ImageDraw, ImageFont

        font = ImageFont.load_default(size=22)
        img = Image.new("RGB", (360, 360), self.rng.choice(["#f3eefc", "#e0f2fe", "#fef3c7", "#dcfce7"]))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 350, 350], outline="#5c418c", width=3)
        for n, text in enumerate(["CONTOH FOTO TAHAP", "(data demo)", "", step_name[:26], f"{booking.pet_name} · #{booking.pk}"]):
            draw.text((28, 60 + n * 46), text, fill="#2b3674", font=font)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=75)
        return ContentFile(buf.getvalue(), name=f"contoh-tahap-{booking.pk}.jpg")

    def _work(self, booking, groomer, started, photos=False, upto=None):
        """Jalankan tahapan kerja: start + selesaikan `upto` tahap (None = semua) mundur ke waktu `started`."""
        booking.start(groomer)
        steps = list(booking.steps.order_by("position"))
        upto = len(steps) if upto is None else upto
        per = max(5, booking.service.duration_minutes // max(1, len(steps)))
        for n, step in enumerate(steps[:upto], start=1):
            step.done_at = started + timedelta(minutes=per * n)
            step.done_by = groomer
            if n == len(steps):
                step.note = self.rng.choice(GROOMER_NOTES)
            if photos and step.needs_photo:
                step.photo.save(f"demo-tahap-{booking.pk}-{n}.jpg", self.demo_step_photo(booking, step.name, step.done_at), save=False)
            step.save()
        updates = {"started_at": started}
        if upto == len(steps):
            updates.update(
                status=BookingStatus.READY,
                finished_at=started + timedelta(minutes=per * len(steps)),
                groomer_note=steps[-1].note,
            )
        ServiceBooking.objects.filter(pk=booking.pk).update(**updates)
        booking.refresh_from_db()

    def seed_bookings(self, customers, groomers, cashier, count=48, no_photos=False):
        if ServiceBooking.objects.filter(customer__in=customers).exists():
            self.stdout.write("Booking layanan demo sudah ada, dilewati.")
            return
        services = list(Service.objects.active())
        if not services or not groomers:
            return
        pets = self.seed_pets(customers)
        now = timezone.now().replace(second=0, microsecond=0)
        today_open = timezone.localtime(now).replace(hour=9, minute=0)
        demo = customers[-1]
        # Alur per booking. Riwayat lama: selesai / batal / tidak datang; hari ini: antrean, dikerjakan, siap.
        plan = (["done"] * 5 + ["cancelled", "no_show", "done_delivery"]) * 4
        plan += ["queued", "queued", "queued", "process", "process", "ready", "pending", "pending", "scheduled", "scheduled", "scheduled_pickup"]
        plan = plan[:count] if count < len(plan) else plan
        demo_photos = not no_photos
        for i, status in enumerate(plan):
            customer = self.rng.choice(customers[:-1] or customers)
            pet = None
            if i in (2, 8) or status == "scheduled_pickup":
                customer = demo
                # Kopi: grooming terakhir 40 hari lalu (muncul pengingat); Mochi: riwayat lengkap & sedang dijemput.
                pet = next((p for p in pets[demo.pk] if p.name == ("Kopi" if i == 2 else "Mochi")), None)
            pet = pet or self.rng.choice(pets[customer.pk])
            options = [s for s in services if s.suits(pet.pet_type)] or services
            service = self.rng.choice(options)
            if status in ("done", "done_delivery", "cancelled", "no_show"):
                schedule = now - timedelta(days=self.rng.randint(2, 60))
                if customer == demo and i == 2:
                    schedule = now - timedelta(days=40)  # Mochi: sudah waktunya grooming lagi
                schedule = timezone.localtime(schedule).replace(hour=self.rng.randint(9, 16), minute=0)
            elif status in ("queued", "process", "ready"):
                schedule = today_open + timedelta(minutes=30 * i % 300)
                schedule = min(schedule, now - timedelta(minutes=10))
            else:
                schedule = timezone.localtime(now + timedelta(days=self.rng.randint(1, 6))).replace(hour=self.rng.randint(9, 16), minute=0)
            transport = {}
            if status in ("done_delivery", "scheduled_pickup"):
                transport = dict(pickup=True, return_trip=True, location=self.customer_point(customer), address=customer.address)
            booking = ServiceBooking.book(
                customer=customer, service=service, pet=pet, pet_name=pet.name, pet_type=pet.pet_type,
                schedule=schedule, created_by=customer if status == "pending" else cashier,
                note=self.rng.choice(BOOKING_NOTES), confirmed=status != "pending", **transport,
            )
            ServiceBooking.objects.filter(pk=booking.pk).update(created_at=schedule - timedelta(days=self.rng.randint(1, 3)))
            if status in ("pending", "scheduled"):
                continue
            pet_courier = User.pet_couriers().order_by("?").first()
            if transport and pet_courier:
                booking.assign_pet_courier(pet_courier)
            if status == "scheduled_pickup":
                continue  # dijalankan di seed_pet_trip supaya jejak GPS kurir konsisten
            if status == "cancelled":
                booking.cancel(reason=self.rng.choice(["Jadwal bentrok atau berhalangan", "Hewan sedang sakit", "Ingin ganti layanan atau jadwal"]), by=booking.customer)
                ServiceBooking.objects.filter(pk=booking.pk).update(cancelled_at=schedule - timedelta(hours=self.rng.randint(2, 24)))
                continue
            if status == "no_show":
                booking.mark_no_show()
                continue
            groomer = self.rng.choice(groomers)
            weight = pet.weight_kg
            condition = self.rng.choice(["Sehat", "Sehat, bulu agak kusut", "Ada sedikit kutu", "Kuku panjang", "Sehat, agak gelisah"])
            if transport:
                ServiceBooking.objects.filter(pk=booking.pk).update(
                    status=BookingStatus.PICKUP, transport_started_at=schedule - timedelta(minutes=40),
                    pet_collected_at=schedule - timedelta(minutes=20),
                )
                booking.refresh_from_db()
            booking.check_in(cashier, weight, condition)
            checked = schedule + timedelta(minutes=self.rng.randint(0, 10))
            ServiceBooking.objects.filter(pk=booking.pk).update(checked_in_at=checked)
            if status == "queued":
                continue
            started = checked + timedelta(minutes=self.rng.randint(5, 25))
            photos = demo_photos and (customer == demo or status in ("process", "ready"))
            if status == "process":
                booking.groomer = groomer
                self._work(booking, groomer, now - timedelta(minutes=25 + 10 * i % 30), photos=photos, upto=self.rng.randint(1, 2))
                continue
            self._work(booking, groomer, started, photos=photos)
            if status == "ready":
                continue
            done_at = booking.finished_at + timedelta(minutes=self.rng.randint(15, 90))
            ServiceBooking.objects.filter(pk=booking.pk).update(status=BookingStatus.DONE, closed_at=done_at)
            if transport:
                ServiceBooking.objects.filter(pk=booking.pk).update(transport_started_at=booking.finished_at + timedelta(minutes=10))
            if self.rng.random() < 0.7:
                stars = self.rng.choices([5, 4, 3, 2], weights=[60, 25, 10, 5])[0]
                ServiceBooking.objects.filter(pk=booking.pk).update(
                    rating=stars, rated_at=done_at + timedelta(hours=2),
                    review=self.rng.choice(["Wangi dan rapi, terima kasih!", "Groomernya sabar.", "Agak lama menunggu.", "", "Kucing saya jadi bersih."]) if stars >= 3 else "Kuku dipotong terlalu pendek.",
                )
        # Nomor antrean dihitung ulang per hari check-in (tanggalnya sudah dimundurkan di atas).
        checked = list(ServiceBooking.objects.filter(checked_in_at__isnull=False).order_by("checked_in_at", "pk"))
        ServiceBooking.objects.filter(pk__in=[b.pk for b in checked]).update(queue_seq=None)
        per_day = {}
        for b in checked:
            day = timezone.localtime(b.checked_in_at).date()
            per_day[day] = per_day.get(day, 0) + 1
            ServiceBooking.objects.filter(pk=b.pk).update(queue_date=day, queue_seq=per_day[day])

    # ------------------------------------------------- akun pelanggan per fitur

    def seed_feature_accounts(self, password, admins, couriers, cashier, groomers, demo, no_photos):
        """Akun pelanggan yang masing-masing fokus satu fitur, plus pelengkap demo_customer.
        Mengembalikan {username: pelanggan} untuk akun yang baru diisi pada run ini."""
        fresh = {}
        by_name = {u.username: u for u in couriers + groomers}
        for row in FEATURE_CUSTOMERS:
            customer = self.feature_account(row, password)
            if Order.objects.filter(customer=customer).exists() or ServiceBooking.objects.filter(customer=customer).exists():
                continue
            fill = getattr(self, "fill_" + row[0].removeprefix(DEMO_PREFIX))
            fill(customer, admins[0], cashier, by_name, not no_photos)
            fresh[row[0]] = customer
        if not ServiceBooking.objects.filter(customer=demo, status=BookingStatus.PENDING).exists():
            kopi = Pet.objects.filter(owner=demo, name="Kopi").first() or Pet.objects.filter(owner=demo).first()
            if kopi:
                self.feature_booking(demo, kopi, cashier, "pending", days=3)
                self.feature_booking(demo, kopi, cashier, "scheduled", days=6)
        return fresh

    def feature_account(self, row, password):
        username, first, last, phone, address = row
        customer, created = Customer.objects.get_or_create(
            phone_number=phone,
            defaults={
                "username": username, "first_name": first, "last_name": last,
                "address": address, "email": username.replace("_", ".") + "@example.com",
            },
        )
        if created:
            customer.set_password(password)
            customer.save()
        return customer

    def feature_order(self, customer, method, note=""):
        sellable = list(Product.objects.sellable().filter(stock__gt=2, name__in=PRODUCT_NAMES))
        picks = self.rng.sample(sellable, k=min(len(sellable), self.rng.randint(1, 3)))
        return Order.place_online(
            customer, [(p.pk, 1) for p in picks], method, note=note,
            address=customer.address, location=self.customer_point(customer),
        )

    def fill_belanja(self, customer, admin, cashier, staff, photos):
        """Satu pesanan untuk setiap status: dari menunggu konfirmasi sampai diulas & dibatalkan."""
        now = timezone.now()
        T, C = PaymentMethod.TRANSFER, PaymentMethod.CASH

        def ship(order, courier, delivered=False):
            order.confirm(admin)
            if order.payment_method == T:
                order.verify_payment(cashier)
            order.refresh_from_db()
            order.mark_on_delivery(courier)
            if delivered:
                order.mark_delivered(note="Diterima langsung oleh pemesan.")

        cancelled = self.feature_order(customer, C)
        cancelled.cancel_by_customer(customer, reason="Salah pilih produk atau jumlah")
        self.backdate(cancelled, now - timedelta(days=15))

        rated = self.feature_order(customer, T)
        ship(rated, staff["demo_kurir2"], delivered=True)
        self.backdate(rated, now - timedelta(days=9))
        rated.refresh_from_db()
        rated.rate(customer, 5, "Pengiriman cepat, kurir ramah.")

        delivered = self.feature_order(customer, C)
        ship(delivered, staff["demo_kurir3"], delivered=True)
        self.backdate(delivered, now - timedelta(days=3))

        on_way = self.feature_order(customer, C, note="Rumah pagar hitam, depan masjid.")
        ship(on_way, staff["demo_kurir1"])
        self.backdate(on_way, now - timedelta(hours=2))

        # Lunas & sudah dikemas, menunggu diambil kurir 3 di toko.
        packed = self.feature_order(customer, T)
        packed.confirm(admin)
        packed.verify_payment(cashier)
        packed.refresh_from_db()
        packed.mark_packed(cashier)
        packed.assign_courier(staff["demo_kurir3"])
        self.backdate(packed, now - timedelta(hours=3))

        rejected = self.feature_order(customer, T)
        rejected.submit_payment_proof(customer, self.demo_proof(rejected, short=10000))
        rejected.reject_payment(cashier, "Nominal di bukti tidak sama dengan total pesanan. Mohon kirim ulang.")
        self.backdate(rejected, now - timedelta(hours=5))

        proof = self.feature_order(customer, T)
        proof.submit_payment_proof(customer, self.demo_proof(proof))
        self.backdate(proof, now - timedelta(minutes=90))

        unpaid = self.feature_order(customer, T)
        self.backdate(unpaid, now - timedelta(minutes=40))

        waiting = self.feature_order(customer, C, note="Kirim sore setelah jam 4 ya.")
        self.backdate(waiting, now - timedelta(minutes=15))
        # Batas bayar transfer dihitung dari sekarang supaya tidak langsung batal otomatis.
        Order.objects.filter(pk__in=[unpaid.pk, proof.pk, rejected.pk]).update(payment_due_at=now + timedelta(hours=20))

    def feature_booking(self, customer, pet, cashier, status, days=0, groomer=None, photos=False, transport=None):
        """Booking demo dengan status tertentu (pending, scheduled, queued, process, ready, done, cancelled)."""
        services = [s for s in Service.objects.active() if s.suits(pet.pet_type)]
        if not services:
            return None
        now = timezone.now().replace(second=0, microsecond=0)
        if days:
            schedule = timezone.localtime(now + timedelta(days=days)).replace(hour=self.rng.randint(9, 15), minute=0)
        else:
            schedule = now - timedelta(minutes=self.rng.randint(30, 90))
        extra = {}
        if transport:
            extra = dict(pickup=True, return_trip=True, location=self.customer_point(customer), address=customer.address)
        booking = ServiceBooking.book(
            customer=customer, service=self.rng.choice(services), pet=pet, pet_name=pet.name, pet_type=pet.pet_type,
            schedule=schedule, created_by=customer if status == "pending" else cashier,
            note=self.rng.choice(BOOKING_NOTES), confirmed=status != "pending", **extra,
        )
        ServiceBooking.objects.filter(pk=booking.pk).update(created_at=min(now, schedule) - timedelta(days=1))
        if transport:
            booking.assign_pet_courier(transport)
        if status in ("pending", "scheduled"):
            return booking
        if status == "cancelled":
            booking.cancel(reason="Pelanggan tidak bisa dihubungi", by=cashier)
            return booking
        booking.check_in(cashier, pet.weight_kg, "Sehat")
        checked = schedule + timedelta(minutes=5)
        ServiceBooking.objects.filter(pk=booking.pk).update(checked_in_at=checked)
        if status == "queued":
            return booking
        booking.groomer = groomer
        if status == "process":
            self._work(booking, groomer, now - timedelta(minutes=20), photos=photos, upto=1)
            return booking
        self._work(booking, groomer, checked + timedelta(minutes=10), photos=photos)
        if status == "done":
            ServiceBooking.objects.filter(pk=booking.pk).update(
                status=BookingStatus.DONE, closed_at=booking.finished_at + timedelta(minutes=30)
            )
        return booking

    def fill_grooming(self, customer, admin, cashier, staff, photos):
        """Tiga hewan dan satu booking untuk setiap status layanan."""
        today = timezone.localdate()
        pets = {
            name: Pet.objects.create(
                owner=customer, name=name, pet_type=kind, breed=breed, sex=sex, weight_kg=weight,
                birth_date=today - timedelta(days=age), notes=notes,
            )
            for name, kind, breed, sex, weight, age, notes in [
                ("Simba", PetType.CAT, "Persia", "JANTAN", 4.2, 1100, "Takut suara pengering."),
                ("Choco", PetType.DOG, "French Bulldog", "BETINA", 9.6, 800, ""),
                ("Bulbul", PetType.RABBIT, "Holland Lop", "BETINA", 1.8, 500, "Kulit sensitif."),
            ]
        }
        g1, g2 = staff["demo_groomer1"], staff["demo_groomer2"]
        done = self.feature_booking(customer, pets["Simba"], cashier, "done", days=-21, groomer=g1, photos=photos)
        if done:
            done.refresh_from_db()
            done.rate(customer, 5, "Simba wangi dan rapi, groomernya sabar.")
        self.feature_booking(customer, pets["Choco"], cashier, "done", days=-6, groomer=g2, photos=photos)
        self.feature_booking(customer, pets["Bulbul"], cashier, "cancelled", days=-10)
        self.feature_booking(customer, pets["Simba"], cashier, "ready", groomer=g2, photos=photos)
        self.feature_booking(customer, pets["Choco"], cashier, "process", groomer=g1, photos=photos)
        self.feature_booking(customer, pets["Bulbul"], cashier, "queued")
        self.feature_booking(customer, pets["Choco"], cashier, "pending", days=2)
        self.feature_booking(customer, pets["Simba"], cashier, "scheduled", days=4, transport=staff["demo_kurir3"])

    def fill_komplain(self, customer, admin, cashier, staff, photos):
        """Pesanan & layanan yang sudah selesai; komplainnya dibuat di seed_feature_complaints."""
        now = timezone.now()
        for days, method, courier in [(12, PaymentMethod.TRANSFER, "demo_kurir2"), (7, PaymentMethod.CASH, "demo_kurir1"),
                                      (4, PaymentMethod.CASH, "demo_kurir3")]:
            order = self.feature_order(customer, method)
            order.confirm(admin)
            if method == PaymentMethod.TRANSFER:
                order.verify_payment(cashier)
            order.refresh_from_db()
            order.mark_on_delivery(staff[courier])
            order.mark_delivered(note="Dititipkan ke satpam." if days == 4 else "Diterima langsung oleh pemesan.")
            self.backdate(order, now - timedelta(days=days))
        pet = Pet.objects.create(owner=customer, name="Milo", pet_type=PetType.CAT, breed="Domestik", sex="JANTAN",
                                 weight_kg=3.9, birth_date=timezone.localdate() - timedelta(days=1500))
        self.feature_booking(customer, pet, cashier, "done", days=-5, groomer=staff["demo_groomer1"], photos=photos)

    def seed_feature_complaints(self, fresh, cashier):
        """Ulasan & komplain (baru, diproses, selesai) untuk demo_komplain, dan dua komplain demo_customer."""
        komplain = fresh.get("demo_komplain")
        if komplain:
            orders = list(Order.objects.filter(customer=komplain, order_status="TERKIRIM").order_by("date"))
            booking = ServiceBooking.objects.filter(customer=komplain, status=BookingStatus.DONE).first()
            if orders:
                orders[0].rate(komplain, 4, "Barang sesuai, kemasan rapi.")
                orders[-1].rate(komplain, 2, "Kemasan penyok saat sampai.")
            samples = [
                ("PENGIRIMAN", orders[-1] if orders else None, None,
                 "Kardus penyok dan satu kaleng makanan basah bocor.", ComplaintStatus.RESOLVED,
                 "Mohon maaf, kami kirim pengganti besok pagi tanpa biaya."),
                ("LAYANAN", None, booking, "Kuku Milo dipotong terlalu pendek, sempat berdarah sedikit.",
                 ComplaintStatus.IN_PROGRESS, "Kami sedang cek foto tahap potong kuku bersama groomer."),
                ("PRODUK", orders[1] if len(orders) > 1 else None, None,
                 "Pasir kucing yang datang beda merek dari yang saya pesan.", ComplaintStatus.OPEN, ""),
            ]
            self.make_complaints(komplain, samples, cashier)
        demo = User.objects.filter(username=DEMO_CUSTOMER[0]).first()
        if demo and not Complaint.objects.filter(customer=demo).exists():
            order = Order.objects.filter(customer=demo, order_status="TERKIRIM").order_by("-date").first()
            booking = ServiceBooking.objects.filter(customer=demo, status=BookingStatus.DONE).first()
            self.make_complaints(demo, [
                ("PRODUK", order, None, "Tanggal kedaluwarsa makanan tinggal 1 bulan.", ComplaintStatus.RESOLVED,
                 "Terima kasih infonya. Kami tukar dengan stok baru saat pengiriman berikutnya."),
                ("LAYANAN", None, booking, "Bulu bagian ekor masih agak kusut setelah grooming.", ComplaintStatus.OPEN, ""),
            ], cashier)

    def make_complaints(self, customer, samples, cashier):
        for n, (category, order, booking, message, status, response) in enumerate(samples):
            complaint = Complaint.objects.create(
                customer=customer, order=order, booking=booking, category=category, message=message,
                created_at=timezone.now() - timedelta(days=len(samples) - n, hours=3),
            )
            if status != ComplaintStatus.OPEN:
                complaint.respond(cashier, status, response)

    def seed_pet_trip(self, customers):
        """Booking demo_customer yang hewannya sedang dijemput kurir (peta live di Booking Saya)."""
        demo = customers[-1]
        booking = ServiceBooking.objects.filter(
            customer=demo, status=BookingStatus.SCHEDULED, pickup_requested=True
        ).first()
        if booking is None:
            return
        busy = Order.objects.filter(order_status="DALAM_PENGIRIMAN").values_list("courier_id", flat=True)
        courier = User.pet_couriers().exclude(pk__in=list(busy)).first()
        if courier is None:
            return  # semua kurir hewan sedang mengantar paket: biarkan Terjadwal
        now = timezone.now()
        local = timezone.localtime(now)
        ServiceBooking.objects.filter(pk=booking.pk).update(
            pet_courier=courier, status=BookingStatus.PICKUP,
            schedule=local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
            transport_started_at=now - timedelta(minutes=12),
        )
        store = StoreSettings.current()
        start_lat, start_lng = store.location
        end_lat, end_lng = float(booking.transport_latitude), float(booking.transport_longitude)
        CourierLocation.objects.filter(courier=courier, recorded_at__gte=now - timedelta(hours=1)).delete()
        steps = 10
        for n in range(steps + 1):
            f = 0.55 * n / steps
            CourierLocation.objects.create(
                courier=courier,
                latitude=round(start_lat + (end_lat - start_lat) * f, 6),
                longitude=round(start_lng + (end_lng - start_lng) * f, 6),
                accuracy=self.rng.randint(5, 20),
                recorded_at=now - timedelta(seconds=15 + 60 * (steps - n)),
            )
        ActivityLog.record(booking, "Kurir berangkat menjemput", actor=courier)
        Notification.send(demo, f"Kurir menuju rumah Anda untuk menjemput {booking.pet_name}",
                          "Pantau posisinya di Booking Saya.", f"/layanan/booking-saya/#booking-{booking.pk}")

    def seed_reviews_and_complaints(self, customers, cashier):
        """Ulasan pesanan yang sudah sampai + beberapa komplain (baru, diproses, selesai)."""
        if Complaint.objects.filter(customer__in=customers).exists():
            return
        delivered = list(Order.objects.filter(order_status="TERKIRIM", customer__in=customers).order_by("delivered_at"))
        for order in delivered:
            if self.rng.random() < 0.55:
                stars = self.rng.choices([5, 4, 3, 2, 1], weights=[55, 25, 10, 6, 4])[0]
                Order.objects.filter(pk=order.pk).update(
                    rating=stars, rated_at=(order.delivered_at or order.date) + timedelta(hours=3),
                    review=self.rng.choice(["Cepat sampai.", "Kurir ramah.", "Barang sesuai.", "", "Pengemasan rapi."]) if stars >= 3 else "Kemasan penyok saat sampai.",
                )
        samples = [
            ("PENGIRIMAN", "Kemasan penyok dan satu kaleng makanan basah bocor.", ComplaintStatus.RESOLVED,
             "Mohon maaf, kami kirim pengganti besok pagi tanpa biaya. Terima kasih fotonya."),
            ("LAYANAN", "Kuku kucing saya dipotong terlalu pendek, sempat berdarah sedikit.", ComplaintStatus.IN_PROGRESS,
             "Kami sedang cek foto tahap potong kuku bersama groomer. Admin akan menghubungi via WhatsApp."),
            ("PRODUK", "Pasir kucing yang datang beda merek dari yang saya pesan.", ComplaintStatus.OPEN, ""),
        ]
        orders = [o for o in delivered if o.customer_id]
        bookings = list(ServiceBooking.objects.filter(status=BookingStatus.DONE, customer__in=customers))
        for n, (category, message, status, response) in enumerate(samples):
            order = self.rng.choice(orders) if category != "LAYANAN" and orders else None
            booking = self.rng.choice(bookings) if category == "LAYANAN" and bookings else None
            customer = (order or booking).customer if (order or booking) else customers[0]
            complaint = Complaint.objects.create(
                customer=customer, order=order, booking=booking, category=category, message=message,
                created_at=timezone.now() - timedelta(days=3 - n, hours=2),
            )
            if status != ComplaintStatus.OPEN:
                complaint.respond(cashier, status, response)

    @staticmethod
    def needs_demo_file(field, demo_prefix):
        """Kosong, atau file demo tercatat tapi tidak ada di folder media (database disalin tanpa media/).
        File unggahan asli yang hilang tidak diganti contoh: admin perlu mengunggah ulang."""
        if not field:
            return True
        if not field.name.startswith(demo_prefix):
            return False
        return not field.storage.exists(field.name)

    def restore_demo_qris(self, store):
        if self.needs_demo_file(store.qris_image, "store/qris/contoh-qris-demo"):
            store.qris_image.save("contoh-qris-demo.png", self.demo_qris(), save=True)
            return True
        return False

    def restore_media(self):
        """--media-only: pulihkan file demo yang hilang tanpa menambah/mengubah data lain."""
        qris = self.restore_demo_qris(StoreSettings.current())
        photos = 0
        for product in Product.objects.filter(name__in=PRODUCT_NAMES):
            if product.photo and media.is_demo_file(product.photo):
                content = media.product_photo(product.name)
                if content:
                    product.photo.save(content.name, content, save=True)
                    photos += 1
        people = self.seed_people_photos(only_missing=True)
        pets = self.seed_pet_photos(only_missing=True)
        self.stdout.write(
            f"QRIS contoh dipulihkan: {'ya' if qris else 'tidak perlu'} · foto produk: {photos} · "
            f"foto profil: {people} · foto hewan: {pets}"
        )

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
                    "description": PRODUCT_DESCRIPTIONS.get(name, ""),
                },
            )
            if not product.description and name in PRODUCT_DESCRIPTIONS:
                Product.objects.filter(pk=product.pk).update(
                    description=PRODUCT_DESCRIPTIONS[name]
                )
            if created:
                opened = now - timedelta(days=self.rng.randint(HISTORY_DAYS + 5, HISTORY_DAYS + 30))
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
            if not no_photos and media.is_demo_file(product.photo):
                content = media.product_photo(name)
                if content:
                    product.photo.save(content.name, content, save=True)

    def restock(self, admin, when):
        """Produk yang hampir habis diisi ulang, seperti toko sungguhan."""
        for product in Product.objects.sellable().filter(
            name__in=PRODUCT_NAMES, stock__lt=4
        ).exclude(name__in=SOLD_OUT):
            mutation = product.apply_mutation(
                MutationType.IN, self.rng.choice([12, 18, 24]), user=admin,
                note="Restok dari supplier",
            )
            StockMutation.objects.filter(pk=mutation.pk).update(date=when)

    def customer_point(self, customer):
        """Titik rumah pelanggan yang stabil (1,5-9 km dari toko) agar rute & ongkir terlihat nyata."""
        import math

        store = StoreSettings.current()
        rng = random.Random(customer.phone_number)
        km = rng.uniform(1.5, 9)
        bearing = rng.uniform(0, 2 * math.pi)
        lat = float(store.latitude) + (km / 111.0) * math.cos(bearing)
        lng = float(store.longitude) + (km / 111.0) * math.sin(bearing)
        return round(lat, 6), round(lng, 6)

    def demo_proof(self, order, short=0, when=None):
        """Tangkapan layar transfer contoh untuk order (short = kurang bayar, untuk bukti yang ditolak)."""
        bank = BankAccount.objects.filter(is_active=True).order_by("order", "pk").first()
        when = timezone.localtime(when or order.date + timedelta(minutes=18))
        return media.transfer_receipt(
            order.pk, order.total_payment - short, order.customer.name, bank, when,
            f"Order #{order.pk}", f"demo-bukti-{order.pk}.jpg",
        )

    def seed_orders(self, admins, couriers, customers, count, more):
        if Order.objects.filter(admin__in=admins).exists() and not more:
            self.stdout.write(
                "Order demo sudah ada, dilewati (pakai --more-orders untuk menambah)."
            )
            return 0
        now = timezone.now()
        # Tanggal dibuat dulu lalu diurutkan, supaya restok & order berjalan
        # maju sepanjang 90 hari. Order terbaru dibuat paling akhir.
        demo_transfer = count > 1  # satu slot untuk pesanan transfer demo_customer
        count -= int(demo_transfer)
        demo_live = count > 1  # satu slot untuk pesanan demo_customer yang sedang diantar
        count -= int(demo_live)
        recent = min(14, count // 6)  # beberapa order hari ini agar papan staf terisi
        ages = sorted(
            [self.rng.uniform(1, HISTORY_DAYS) for _ in range(count - recent)]
            + [self.rng.uniform(0.01, 0.29) for _ in range(recent)],
            reverse=True,
        )
        made = 0
        for age in ages:
            when = now - timedelta(days=age)
            if age >= 1:  # order lama: jam buka toko 08.00-20.00
                when = timezone.localtime(when).replace(hour=self.rng.randint(8, 19))
            admin = self.rng.choice(admins)
            self.restock(admin, when - timedelta(hours=2))
            sellable = list(
                Product.objects.sellable().filter(stock__gt=0, name__in=PRODUCT_NAMES)
            )
            if not sellable:
                break
            picks = self.rng.sample(sellable, k=min(len(sellable), self.rng.randint(1, 4)))
            lines = [(p.pk, self.rng.randint(1, min(3, p.stock))) for p in picks]
            method = self.rng.choices(
                [PaymentMethod.TRANSFER, PaymentMethod.CASH], weights=[60, 40]
            )[0]
            customer = self.rng.choice(customers)
            online = self.rng.random() < 0.45
            if online:
                order = Order.place_online(
                    customer,
                    lines,
                    method,
                    note=self.rng.choice(ORDER_NOTES) if self.rng.random() < 0.4 else "",
                    address=customer.address,
                    location=self.customer_point(customer),
                )
            else:
                Cart.objects.filter(user=admin).delete()
                cart = Cart.objects.create(user=admin)
                for pk, qty in lines:
                    CartItem.objects.create(cart=cart, product_id=pk, quantity=qty)
                order = cart.checkout(customer=customer, admin=admin, payment_method=method)
                lat, lng = self.customer_point(customer)
                Order.objects.filter(pk=order.pk).update(
                    delivery_latitude=lat,
                    delivery_longitude=lng,
                    delivery_distance_km=round(StoreSettings.current().distance_km(lat, lng), 2),
                )
                order.refresh_from_db()
            self.advance(order, admin, couriers, age)
            self.backdate(order, when)
            made += 1
        # Satu pesanan transfer milik demo_customer yang belum dibayar, agar
        # petunjuk transfer di Pesanan Saya bisa langsung dicoba.
        sellable = list(Product.objects.sellable().filter(stock__gt=1, name__in=PRODUCT_NAMES))
        if demo_transfer and sellable:
            demo = customers[-1]
            Order.place_online(
                demo,
                [(p.pk, 1) for p in self.rng.sample(sellable, k=min(2, len(sellable)))],
                PaymentMethod.TRANSFER,
                address=demo.address,
                location=self.customer_point(demo),
            )
            made += 1
        # Satu pesanan COD milik demo_customer yang sedang diantar demo_kurir1,
        # supaya peta lacak realtime di dasbor pelanggan langsung terlihat.
        sellable = list(Product.objects.sellable().filter(stock__gt=1, name__in=PRODUCT_NAMES))
        kurir1 = next((c for c in couriers if c.username == "demo_kurir1"), None)
        if demo_live and sellable and kurir1:
            demo = customers[-1]
            order = Order.place_online(
                demo,
                [(p.pk, 1) for p in self.rng.sample(sellable, k=min(2, len(sellable)))],
                PaymentMethod.CASH,
                address=demo.address,
                location=self.customer_point(demo),
                note="Tolong telepon dulu sebelum sampai.",
            )
            order.confirm(admins[0])
            order.refresh_from_db()
            order.mark_on_delivery(kurir1)
            made += 1
        self.finish_payments_and_packing(admins)
        return made

    def finish_payments_and_packing(self, admins):
        """Lengkapi data tahap pembayaran & packing untuk order demo yang tanggalnya sudah dimundurkan."""
        cashier = User.objects.filter(username="demo_kasir").first() or admins[0]
        demo_orders = Order.objects.filter(customer__phone_number__in=CUSTOMER_PHONES + ACCOUNT_PHONES)
        for order in demo_orders.filter(payment_method=PaymentMethod.TRANSFER):
            updates = {"payment_due_at": order.date + timedelta(hours=24)}
            if order.payment_status == "LUNAS":
                updates.update(payment_verified_by=cashier, payment_verified_at=order.date + timedelta(minutes=30))
            Order.objects.filter(pk=order.pk).update(**updates)
        # Beberapa transfer terbaru sudah mengirim bukti dan menunggu dicek kasir.
        waiting = (
            demo_orders.filter(payment_method=PaymentMethod.TRANSFER, payment_status="MENUNGGU")
            .exclude(order_status="DIBATALKAN")
            .exclude(customer__username=DEMO_CUSTOMER[0])
            .order_by("-date")[:3]
        )
        for order in waiting:
            order.payment_proof.save(f"demo-bukti-{order.pk}.jpg", self.demo_proof(order), save=False)
            Order.objects.filter(pk=order.pk).update(
                payment_proof=order.payment_proof.name,
                payment_proof_at=order.date + timedelta(minutes=20),
                payment_due_at=timezone.now() + timedelta(hours=20),
            )
        # Transfer belum bayar yang masih baru: batas bayar dihitung dari sekarang supaya tidak langsung batal.
        demo_orders.filter(
            payment_method=PaymentMethod.TRANSFER, payment_status="MENUNGGU", payment_proof=""
        ).exclude(order_status="DIBATALKAN").update(payment_due_at=timezone.now() + timedelta(hours=22))
        # Nomor packing: urut per tanggal konfirmasi, mengikuti tanggal order yang sudah dimundurkan.
        packed = demo_orders.filter(packing_seq__isnull=False).order_by("confirmed_at", "date", "pk")
        per_day = {}
        for order in packed:
            day = timezone.localtime(order.confirmed_at or order.date).date()
            per_day[day] = per_day.get(day, 0) + 1
            updates = {"packing_date": day, "packing_seq": per_day[day]}
            if order.shipped_at:
                updates.update(packed_at=order.shipped_at - timedelta(minutes=15), packed_by=cashier)
            Order.objects.filter(pk=order.pk).update(**updates)
        # Separuh order siap kirim hari ini sudah dikemas, sisanya masih antre.
        for n, order in enumerate(
            demo_orders.filter(order_status="DIKONFIRMASI", packing_seq__isnull=False, packed_at__isnull=True)
        ):
            if n % 2 == 0:
                Order.objects.filter(pk=order.pk).update(packed_at=timezone.now(), packed_by=cashier)

    def advance(self, order, admin, couriers, age):
        """Status mengikuti umur order: order lama sudah selesai, order
        beberapa jam terakhir masih menunggu atau sedang diantar."""
        transfer = order.payment_method == PaymentMethod.TRANSFER
        if age < 0.3:
            status = self.rng.choice(["pending", "confirmed", "on_delivery"])
        elif age < 2:
            status = self.rng.choice(["confirmed", "on_delivery", "delivered", "delivered"])
        else:
            status = self.rng.choices(["delivered", "cancelled"], weights=[86, 14])[0]
        if status == "pending" and order.is_online:
            return  # masih menunggu konfirmasi toko
        if order.is_online and order.order_status == "MENUNGGU":
            if status == "cancelled" and self.rng.random() < 0.5:
                order.cancel_by_customer(order.customer, reason=self.rng.choice(["Ingin ganti alamat atau cara bayar", "Barang sudah tidak dibutuhkan"]))
                return
            order.confirm(admin)
        if status == "cancelled":
            if transfer and self.rng.random() < 0.3:
                order.mark_paid()
            order.cancel(reason=self.rng.choice(["Stok habis", "Pembayaran tidak diterima"]), by=order.admin)
            return
        if status in ("pending", "confirmed"):
            if transfer and self.rng.random() < 0.5:
                order.mark_paid()
            if order.is_ready_to_ship and self.rng.random() < 0.4:
                order.assign_courier(self.rng.choice(couriers))
            return
        if transfer:
            order.mark_paid()  # transfer harus lunas sebelum dikirim
        order.mark_on_delivery(self.rng.choice(couriers))
        if status == "delivered":
            order.mark_delivered(note=self.rng.choice(
                ["Diterima langsung oleh pemesan.", "Diterima keluarga.", "Dititipkan ke satpam.", ""]
            ))

    def backdate(self, order, when):
        order.refresh_from_db()
        updates = {"date": when}
        if order.confirmed_at:
            updates["confirmed_at"] = when + timedelta(minutes=self.rng.randint(5, 40))
        if order.shipped_at:
            updates["shipped_at"] = when + timedelta(minutes=self.rng.randint(45, 120))
        if order.delivered_at:
            updates["delivered_at"] = updates["shipped_at"] + timedelta(minutes=self.rng.randint(20, 90))
        Order.objects.filter(pk=order.pk).update(**updates)
        StockMutation.objects.filter(note__startswith=f"Order #{order.pk}").update(date=when)

    def seed_courier_tracks(self, couriers):
        """Pengiriman yang sedang berjalan: jejak GPS dari toko menuju tujuan
        berikutnya (beberapa menit terakhir) dan urutan rute terdekat -> terjauh."""
        from courier import routing

        now = timezone.now()
        store = StoreSettings.current()
        busy = Order.objects.filter(order_status="DALAM_PENGIRIMAN", courier__in=couriers)
        for courier in {o.courier for o in busy}:
            if CourierLocation.objects.filter(courier=courier, recorded_at__gte=now - timedelta(hours=1)).exists():
                continue
            mine = busy.filter(courier=courier)
            # Paket yang sedang dibawa berangkat bersama dari toko 30-40 menit lalu.
            left_at = now - timedelta(minutes=self.rng.randint(30, 40))
            for order in mine:
                Order.objects.filter(pk=order.pk).update(
                    shipped_at=left_at, packed_at=left_at - timedelta(minutes=15)
                )
            first = routing.reroute(courier, start=store.location)[0]
            target = Order.objects.get(pk=first)
            start_lat, start_lng = store.location
            end_lat = float(target.delivery_latitude or start_lat)
            end_lng = float(target.delivery_longitude or start_lng)
            steps = 14
            progress = self.rng.uniform(0.45, 0.7)  # baru separuh jalan ke tujuan pertama
            for n in range(steps + 1):
                f = progress * n / steps
                wobble = self.rng.uniform(-0.0004, 0.0004)
                CourierLocation.objects.create(
                    courier=courier,
                    latitude=round(start_lat + (end_lat - start_lat) * f + wobble, 6),
                    longitude=round(start_lng + (end_lng - start_lng) * f - wobble, 6),
                    accuracy=self.rng.randint(5, 20),
                    recorded_at=now - timedelta(seconds=20 + 100 * (steps - n)),
                )
            routing.reroute(courier)

    def seed_cod_and_remittances(self, couriers, cashier):
        """Uang COD yang dipegang kurir: order lama sudah disetor & diterima kasir,
        setoran terakhir kurir 2 masih menunggu kasir, sisanya masih di tangan kurir."""
        from courier.models import CashRemittance, RemittanceStatus

        delivered = Order.objects.filter(
            order_status="TERKIRIM", payment_method=PaymentMethod.CASH, courier__in=couriers
        ).exclude(channel="TOKO", delivery_latitude__isnull=True)
        for order in delivered:
            Order.objects.filter(pk=order.pk).update(
                cash_collected=order.total_payment,
                handover_verified=True,
                delivered_latitude=order.delivery_latitude,
                delivered_longitude=order.delivery_longitude,
            )
        if CashRemittance.objects.filter(courier__in=couriers).exists():
            return
        for courier in couriers:
            mine = Order.objects.filter(
                courier=courier, cash_collected__gt=0, remittance__isnull=True, delivered_at__isnull=False
            ).order_by("delivered_at")
            per_day = {}
            for order in mine:
                per_day.setdefault(timezone.localtime(order.delivered_at).date(), []).append(order)
            latest = max(per_day, default=None)
            for day, orders in sorted(per_day.items()):
                if day == latest and courier.username != "demo_kurir2":
                    continue  # uang pengantaran terakhir masih dipegang kurir (lihat menu Setoran)
                amount = sum(o.cash_collected for o in orders)
                submitted = max(o.delivered_at for o in orders) + timedelta(minutes=30)
                remittance = CashRemittance.objects.create(courier=courier, amount=amount, submitted_at=submitted)
                if day != latest:
                    short = self.rng.random() < 0.08
                    CashRemittance.objects.filter(pk=remittance.pk).update(
                        status=RemittanceStatus.RECEIVED,
                        received_by=cashier,
                        received_at=submitted + timedelta(minutes=10),
                        received_amount=amount - (2000 if short else 0),
                        note="Kurang Rp 2.000, kurir tidak punya kembalian." if short else "",
                    )
                Order.objects.filter(pk__in=[o.pk for o in orders]).update(remittance=remittance)

    # ---------------------------------------------------------------- kasir (offline)

    def demo_qris(self):
        """Gambar QRIS CONTOH (bukan QRIS asli): QR berisi teks peringatan + label besar."""
        import qrcode
        from PIL import ImageDraw

        qr = qrcode.make("CONTOH QRIS DATA DEMO - BUKAN UNTUK PEMBAYARAN").get_image().convert("RGB")
        qr = qr.resize((360, 360))
        canvas = Image.new("RGB", (420, 500), "white")
        canvas.paste(qr, (30, 70))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 420, 56), fill=(200, 0, 0))
        draw.text((20, 10), "CONTOH QRIS - DATA DEMO", fill="white")
        draw.text((20, 30), "Ganti dengan QRIS asli toko di Pengaturan Toko", fill="white")
        draw.text((20, 445), "Bukan QRIS sungguhan: jangan dipakai membayar.", fill=(200, 0, 0))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return ContentFile(buf.getvalue())

    def seed_pos(self, admins, cashier, customers):
        """Transaksi kasir 4 hari terakhir: shift buka/tutup (satu selisih), bayar campuran,
        diskon, satu dibatalkan, retur menunggu & disetujui, pembayaran grooming, dan satu transaksi parkir."""
        from transaction import pos
        from transaction.models import CashierShift, Fulfillment, HeldSale, ShiftStatus

        pos.assign_codes()
        store = StoreSettings.current()
        self.restore_demo_qris(store)
        if Order.objects.filter(receipt_no__isnull=False, admin__username__startswith=DEMO_PREFIX).exists():
            return
        admin = admins[0]
        now = timezone.now()
        seq = {}

        def products():
            return list(Product.objects.sellable().filter(stock__gt=3, name__in=PRODUCT_NAMES))

        def sale(user, shift, when, customer=None, booking=None, **pay):
            Cart.objects.filter(user=user).delete()
            cart = Cart.objects.create(user=user)
            for p in self.rng.sample(products(), k=self.rng.randint(1, 3)):
                CartItem.objects.create(cart=cart, product=p, quantity=self.rng.randint(1, 2))
            if booking is not None:
                cart.add_service(booking)
            total = pos.quote(cart, pay.get("discount", 0))["total"]
            for key in ("pay_transfer", "pay_qris"):
                if key in pay:
                    pay[key] = min(pay[key], total)
            noncash = pay.get("pay_transfer", 0) + pay.get("pay_qris", 0)
            if pay.pop("qris_all", False):
                pay["pay_qris"], noncash = total, total
            due = total - noncash
            cash = due if due <= 0 else -(-due // 50000) * 50000 if self.rng.random() < 0.6 else due
            order = pos.checkout(
                cart, user, customer=customer, cash_received=cash,
                noncash_confirmed=bool(noncash), **pay,
            )
            day = timezone.localtime(when).date()
            seq[day] = seq.get(day, 0) + 1
            receipt = f"STR-{day:%y%m%d}-{seq[day]:04d}"
            StockMutation.objects.filter(note=f"Struk {order.receipt_no}").update(date=when, note=f"Struk {receipt}")
            Order.objects.filter(pk=order.pk).update(
                receipt_no=receipt, date=when, delivered_at=when, confirmed_at=when, payment_verified_at=when,
            )
            order.refresh_from_db()
            return order

        def open_shift(user, when, float_cash):
            shift = pos.open_shift(user, float_cash)
            CashierShift.objects.filter(pk=shift.pk).update(opened_at=when)
            shift.refresh_from_db()
            return shift

        def close_shift(shift, when, short=0, note=""):
            CashierShift.objects.filter(pk=shift.pk).update(closed_at=when)
            shift.refresh_from_db()
            expected = shift.summary()["expected_cash"]
            CashierShift.objects.filter(pk=shift.pk).update(
                status=ShiftStatus.CLOSED, expected_cash=expected, counted_cash=expected - short,
                difference=-short, close_note=note,
            )

        bookings = list(
            ServiceBooking.objects.filter(status__in=[BookingStatus.DONE, BookingStatus.READY])
            .exclude(payment_lines__isnull=False).order_by("-schedule")[:3]
        )
        registered = [c for c in customers if c.address]
        voided = returned = None
        # Tiga hari lalu sampai kemarin: shift kasir ditutup; kemarin ada selisih.
        for days_ago in (3, 2, 1):
            day = timezone.localtime(now - timedelta(days=days_ago)).replace(hour=8, minute=0, second=0, microsecond=0)
            shift = open_shift(cashier, day, 200000)
            for n in range(self.rng.randint(4, 6)):
                when = day + timedelta(minutes=30 + n * 70 + self.rng.randint(0, 40))
                kind = self.rng.random()
                customer = self.rng.choice(registered) if self.rng.random() < 0.3 else None
                if kind < 0.15:
                    order = sale(cashier, shift, when, customer, qris_all=True)
                elif kind < 0.3:
                    order = sale(cashier, shift, when, customer, pay_transfer=20000)
                elif kind < 0.4:
                    order = sale(cashier, shift, when, customer, discount=5000, discount_reason="Pelanggan setia")
                else:
                    order = sale(cashier, shift, when, customer, buyer_name="" if customer else self.rng.choice(["", "Pak Joko", "Bu Lina"]))
                if days_ago == 2 and voided is None:
                    voided = pos.void(order, admin, "Pembeli batal, barang dikembalikan ke rak")
                    Order.objects.filter(pk=order.pk).update(voided_at=when + timedelta(minutes=5))
                elif days_ago == 3 and returned is None and order.details.exists():
                    returned = order
            if bookings:
                booking = bookings.pop()
                sale(cashier, shift, day + timedelta(hours=9), customer=booking.customer, booking=booking)
            close = day + timedelta(hours=11, minutes=30)
            if days_ago == 1:
                close_shift(shift, close, short=5000, note="Kurang Rp 5.000, kemungkinan salah kembalian.")
            else:
                close_shift(shift, close)
        # Hari ini: shift kasir masih buka, beberapa transaksi, satu diantar kurir.
        today = timezone.localtime(now).replace(hour=8, minute=0, second=0, microsecond=0)
        if today > now:
            today = now - timedelta(hours=2)
        shift = open_shift(cashier, today, 250000)
        for n in range(3):
            when = min(now - timedelta(minutes=5), today + timedelta(minutes=20 + n * 25))
            sale(cashier, shift, when, pay_qris=10000) if n == 1 else sale(cashier, shift, when)
        demo = customers[-1]
        if demo.address:
            Cart.objects.filter(user=cashier).delete()
            cart = Cart.objects.create(user=cashier)
            CartItem.objects.create(cart=cart, product=products()[0], quantity=1)
            order = pos.checkout(
                cart, cashier, customer=demo, fulfillment=Fulfillment.DELIVERY,
                cash_received=pos.quote(cart, 0, 8000)["total"], shipping_fee=8000,
                note="Dibeli di toko, minta diantar sore.",
            )
            Order.objects.filter(pk=order.pk).update(delivery_latitude=self.customer_point(demo)[0],
                                                     delivery_longitude=self.customer_point(demo)[1])
        # Retur: satu disetujui (dari 3 hari lalu), satu menunggu admin (hari ini).
        if returned is not None:
            detail = returned.details.first()
            req = pos.request_return(returned, cashier, {detail.pk: 1}, "Kemasan sobek saat dibuka di rumah")
            pos.decide_return(req, admin, True, "Kemasan memang rusak, diganti uang")
        latest = Order.objects.filter(shift=shift, fulfillment=Fulfillment.TAKE_AWAY, details__isnull=False).first()
        if latest is not None:
            detail = latest.details.first()
            pos.request_return(latest, cashier, {detail.pk: 1}, "Salah rasa, minta tukar")
        # Transaksi parkir: pembeli masih mengambil barang lain.
        Cart.objects.filter(user=cashier).delete()
        cart = Cart.objects.create(user=cashier)
        for p in products()[:2]:
            CartItem.objects.create(cart=cart, product=p, quantity=1)
        pos.hold(cart, cashier, "Bu Rina (masih pilih pasir)")
        HeldSale.objects.filter(cashier=cashier).update(created_at=now - timedelta(minutes=12))

    def seed_customer_notifications(self, usernames):
        """Notifikasi pesanan & booking untuk akun pelanggan yang baru diisi pada run ini."""
        for user in User.objects.filter(username__in=usernames):
            self.notify_customer(user)

    def notify_customer(self, user):
        for booking in ServiceBooking.objects.filter(customer=user, status=BookingStatus.READY):
            Notification.send(user, f"{booking.pet_name} sudah selesai dan siap diambil",
                              "Lihat foto tiap tahap di Booking Saya.", f"/layanan/booking-saya/#booking-{booking.pk}")
        for order in Order.objects.filter(customer=user).order_by("date"):
            url = f"/lacak/{order.tracking_number}/"
            if order.order_status == "DALAM_PENGIRIMAN":
                Notification.send(user, f"Pesanan #{order.pk} sedang diantar", "Pantau posisi kurir di peta.", url)
            elif order.order_status == "TERKIRIM":
                Notification.objects.create(
                    user=user, title=f"Pesanan #{order.pk} sudah sampai", url=url, read_at=timezone.now()
                )
            elif order.payment_reject_note:
                Notification.send(
                    user, f"Bukti transfer pesanan #{order.pk} ditolak",
                    order.payment_reject_note, "/pesanan-saya/",
                )
            elif order.payment_method == "TRANSFER" and order.payment_status == "MENUNGGU" and order.order_status != "DIBATALKAN" and not order.payment_proof:
                Notification.send(
                    user, f"Menunggu pembayaran pesanan #{order.pk}",
                    "Transfer ke rekening toko lalu kirim foto bukti.", "/dasbor/",
                )

    # ----- Foto & bukti -------------------------------------------------
    def seed_people_photos(self, only_missing=False):
        """Foto profil staf & sebagian besar pelanggan (tidak semua orang mengunggah foto)."""
        staff = [r[0] for r in SUPERADMINS + ADMINS + CASHIERS + GROOMERS + COURIERS] + [r[0] for r in PENDING_STAFF]
        accounts = [DEMO_CUSTOMER[0]] + [row[0] for row in FEATURE_CUSTOMERS]
        users = list(User.objects.filter(username__in=staff + accounts))
        users.sort(key=lambda u: (staff + accounts).index(u.username))
        plain = User.objects.filter(role=Role.CUSTOMER, is_walk_in=False, phone_number__in=CUSTOMER_PHONES).order_by("pk")
        users += [u for u in plain if u.pk % 3]
        done = 0
        for n, user in enumerate(users, start=1):
            if only_missing:
                if not user.photo or not media.is_demo_file(user.photo):
                    continue
            elif user.photo:
                continue
            content = media.avatar(n)
            if not content:
                continue
            user.photo.save(content.name, content, save=False)
            User.objects.filter(pk=user.pk).update(photo=user.photo.name)
            done += 1
            profile = CourierProfile.objects.filter(user=user).first()
            if profile and (not profile.photo or media.is_demo_file(profile.photo)):
                profile.photo.save(content.name, media.avatar(n), save=False)
                CourierProfile.objects.filter(pk=profile.pk).update(photo=profile.photo.name)
        return done

    def seed_pet_photos(self, only_missing=False):
        """Foto hewan untuk ras yang punya foto cocok; hewan akun demo selalu diberi foto."""
        accounts = {DEMO_CUSTOMER[0]} | {row[0] for row in FEATURE_CUSTOMERS}
        done = 0
        for pet in Pet.objects.select_related("owner").filter(breed__in=list(media.BREED_PHOTOS)):
            if only_missing:
                if not pet.photo or not media.is_demo_file(pet.photo):
                    continue
            elif pet.photo or (pet.pk % 3 == 0 and pet.owner.username not in accounts):
                continue
            content = media.pet_photo(pet.breed, pet.pk, name=f"demo-hewan-{pet.pk}.jpg")
            if content:
                pet.photo.save(content.name, content, save=False)
                Pet.objects.filter(pk=pet.pk).update(photo=pet.photo.name)
                done += 1
        return done

    def seed_media(self):
        """Lengkapi foto yang di alur nyata selalu ada: bukti transfer yang sudah lunas,
        foto serah terima paket, dan foto hewan saat check-in / dijemput / diantar pulang."""
        self.seed_people_photos()
        self.seed_pet_photos()
        demo_orders = Order.objects.filter(customer__phone_number__in=CUSTOMER_PHONES + ACCOUNT_PHONES)
        for order in demo_orders.filter(
            channel="ONLINE", payment_method=PaymentMethod.TRANSFER, payment_status="LUNAS", payment_proof=""
        ):
            paid = (order.confirmed_at or order.date) + timedelta(minutes=12)
            order.payment_proof.save(f"demo-bukti-{order.pk}.jpg", self.demo_proof(order, when=paid), save=False)
            Order.objects.filter(pk=order.pk).update(payment_proof=order.payment_proof.name, payment_proof_at=paid)
        for order in demo_orders.filter(order_status="TERKIRIM", delivery_photo="").exclude(fulfillment="BAWA"):
            when = timezone.localtime(order.delivered_at or order.date)
            receiver = order.customer.first_name or order.customer.name
            photo = media.delivery_photo(order, [f"Diterima: {receiver[:24]}", f"Order #{order.pk} · {when:%d/%m/%Y %H:%M}"])
            if photo:
                order.delivery_photo.save(photo.name, photo, save=False)
                Order.objects.filter(pk=order.pk).update(delivery_photo=order.delivery_photo.name)
        bookings = ServiceBooking.objects.filter(customer__phone_number__in=CUSTOMER_PHONES + ACCOUNT_PHONES).select_related("pet")
        for b in bookings:
            breed = b.pet.breed if b.pet else ""
            updates = {}
            shots = [
                ("checkin_photo", b.checked_in_at, "Check-in" + (f" · {b.checkin_weight_kg} kg" if b.checkin_weight_kg else "")),
                ("pickup_photo", b.pet_collected_at, "Dijemput kurir"),
                ("return_photo", b.closed_at if b.return_requested else None, "Diantar pulang"),
            ]
            for n, (field, when, label) in enumerate(shots):
                if not when or getattr(b, field):
                    continue
                when = timezone.localtime(when)
                photo = media.pet_photo(breed, b.pk + n, stamp=[f"{label} · {b.pet_name}", f"{when:%d/%m/%Y %H:%M}"],
                                        name=f"demo-{field.split('_')[0]}-{b.pk}.jpg")
                if photo:
                    getattr(b, field).save(photo.name, photo, save=False)
                    updates[field] = getattr(b, field).name
            if updates:
                ServiceBooking.objects.filter(pk=b.pk).update(**updates)

    def summary(self, made, password):
        self.stdout.write(self.style.SUCCESS("Data demo siap."))
        rows = [
            ("Produk", Product.objects.count()),
            ("Mutasi stok", StockMutation.objects.count()),
            ("Pelanggan", Customer.objects.count()),
            ("Order", f"{Order.objects.count()} (+{made} baru)"),
            ("Booking layanan", ServiceBooking.objects.count()),
            ("Titik lokasi kurir", CourierLocation.objects.count()),
            ("Setoran COD", CashRemittance.objects.count()),
            ("Hewan pelanggan", Pet.objects.count()),
            ("Komplain", Complaint.objects.count()),
        ]
        for label, value in rows:
            self.stdout.write(f"  {label:<20}: {value}")
        self.stdout.write(f"  Kata sandi semua akun demo: {password}")
        for username, role in [
            ("demo_superadmin", "Super Admin (juga bisa buka /admin/)"),
            ("demo_admin", "Admin"),
            ("demo_kasir", "Kasir"),
            ("demo_kurir1", "Kurir"),
            ("demo_groomer1", "Groomer"),
            ("demo_customer", "Pelanggan (semua fitur pelanggan)"),
            ("demo_belanja", "Pelanggan (semua status pesanan)"),
            ("demo_grooming", "Pelanggan (semua status booking)"),
            ("demo_komplain", "Pelanggan (ulasan & komplain)"),
        ]:
            self.stdout.write(f"  {username:<15} {role}")
