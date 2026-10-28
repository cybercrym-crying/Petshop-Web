import json
import secrets
from datetime import timedelta

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.views.decorators.http import require_POST
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from product.models import PetType, Product, ProductCondition
from account.decorators import roleRequired
from account.models import Customer, Role
from common.exceptions import PetshopError
from courier.models import CourierLocation
from store.models import StoreSettings
from transaction.models import (
    ONLINE_PAYMENT_METHODS,
    Order,
    OrderStatus,
    PaymentMethod,
    InvalidTransition,
    PriceChanged,
    normalize_tracking_number,
)

from .templatetags.customer_extras import CONDITION_LABEL, CATEGORY_LABELS, PET_LABEL

# Nomor WhatsApp admin (format internasional tanpa +), dipakai tombol kontak dan pesanan.


# Banner promo di Beranda. Isi dict {"title": ..., "text": ...} hanya bila promo
# itu benar-benar berlaku; sistem belum punya mesin diskon, jadi bawaannya None
# (banner diganti ajakan memesan biasa).
SPECIAL_OFFER = None
STORE_ADDRESS = ""


def _site_context(**extra):
    """Data toko (WhatsApp, rekening) dari Pengaturan Toko yang diisi admin."""
    store = StoreSettings.current()
    return {
        "wa_link": store.whatsapp_link,
        "wa_display": store.whatsapp_display,
        "bank_accounts": store.bank_accounts(),
        "store_qris": store.qris,
        **extra,
    }


HOME_PRODUCTS = 4
HOME_SERVICES = 3


def home(request):
    from service.models import Service

    # Landing page hanya untuk pengunjung; pelanggan yang sudah masuk langsung ke dasbornya.
    if request.user.is_authenticated and request.user.role == Role.CUSTOMER:
        return redirect("customer:dashboard")
    popular = (
        Product.objects.sellable()
        .filter(stock__gt=0)
        .select_related("category")
        .annotate(sold=_sold_units())
        .order_by("-sold", "name")[:HOME_PRODUCTS]
    )
    return render(
        request,
        "customer/home.html",
        _site_context(
            active_page="home",
            offer=SPECIAL_OFFER,
            popular_products=popular,
            services=Service.objects.active().order_by("price")[:HOME_SERVICES],
        ),
    )


def about(request):
    stats = {
        "products": Product.objects.sellable().count(),
        "orders": Order.objects.filter(order_status=OrderStatus.DELIVERED).count(),
        "customers": Customer.objects.count(),
    }
    return render(
        request,
        "customer/about.html",
        _site_context(
            active_page="about", stats=stats, store_address=STORE_ADDRESS, store=StoreSettings.current()
        ),
    )


def cart_page(request):
    return render(request, "customer/cart.html", _site_context(active_page="cart"))


# Kategori di halaman Belanja: kode (sama dengan Category.name di database) -> gambar.
CATEGORY_IMAGES = {
    "MAKANAN": "customer/img/category-food.jpg",
    "PERLENGKAPAN": "customer/img/category-equipment.jpg",
    "AKSESORIS": "customer/img/category-accessories.jpg",
    "KESEHATAN": "customer/img/category-health.jpg",
    "MAINAN": "customer/img/category-toys.jpg",
}
DEFAULT_CATEGORY_IMAGE = "customer/img/product-placeholder.svg"
POPULAR_LIMIT = 8


def _category_cards(products):
    counts = {}
    for product in products:
        code = str(product.category.name).upper()
        counts[code] = counts.get(code, 0) + 1
    # Urutan tetap untuk kategori utama, kategori lain menyusul.
    codes = [c for c in CATEGORY_IMAGES if c in counts]
    codes += sorted(c for c in counts if c not in CATEGORY_IMAGES)
    return [
        {
            "code": code,
            "label": CATEGORY_LABELS.get(code, code.title()),
            "image": CATEGORY_IMAGES.get(code, DEFAULT_CATEGORY_IMAGE),
            "count": counts[code],
        }
        for code in codes
    ]


def shop(request):
    """Home Shop: hero, kategori, produk populer. Dengan ?q= atau ?category=
    halaman yang sama menampilkan daftar produk hasil filter."""
    if request.GET.get("wishlist") == "1":
        return redirect("customer:wishlist", permanent=True)
    products_list = list(
        Product.objects.sellable().select_related("category").order_by("name")
    )
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip().upper()

    results = None
    results_title = ""
    if query or category:
        results = products_list
        if category:
            results = [p for p in results if str(p.category.name).upper() == category]
            results_title = CATEGORY_LABELS.get(category, category.title())
        if query:
            results = [p for p in results if query.lower() in p.name.lower()]
            results_title = f"Hasil pencarian “{query}”"

    return render(
        request,
        "customer/home_shop.html",
        _site_context(
            active_page="shop",
            query=query,
            categories=_category_cards(products_list),
            popular_products=products_list[:POPULAR_LIMIT],
            results=results,
            results_title=results_title,
        ),
    )


WISHLIST_MAX_ITEMS = 100


def _parse_ids(raw):
    ids = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
        if len(ids) >= WISHLIST_MAX_ITEMS:
            break
    return ids


def wishlist(request):
    return render(
        request,
        "customer/wishlist.html",
        _site_context(
            active_page="wishlist",
            items_url=reverse("customer:wishlist_items"),
        ),
    )


@never_cache
def wishlist_items(request):
    ids = _parse_ids(request.GET.get("ids"))
    by_id = Product.objects.sellable().select_related("category").in_bulk(ids)
    items = [by_id[pk] for pk in ids if pk in by_id]
    return render(request, "customer/_wishlist_items.html", {"items": items})


CART_CHECK_MAX = 100


@never_cache
def cart_check(request):
    """Harga & stok terbaru untuk isi keranjang di browser (?ids=1,2,3).

    Keranjang disimpan di localStorage, jadi harga di sana bisa basi. Halaman
    keranjang & checkout memanggil ini supaya yang dilihat pelanggan sama dengan
    yang nanti dihitung server.
    """
    ids = _parse_ids(request.GET.get("ids"))[:CART_CHECK_MAX]
    by_id = Product.objects.sellable().in_bulk(ids)
    items = []
    for pk in ids:
        product = by_id.get(pk)
        if product is None:
            items.append({"id": pk, "available": False})
            continue
        items.append(
            {
                "id": pk,
                "available": product.stock > 0,
                "name": product.name,
                "price": product.selling_price,
                "stock": product.stock,
                "photo": product.photo.url if product.photo else "",
                "url": reverse("customer:product_detail", args=[pk]),
            }
        )
    return JsonResponse({"items": items})


PRODUCTS_PER_PAGE = 12
SORT_OPTIONS = [
    ("popular", _lazy("Terpopuler")),
    ("newest", _lazy("Terbaru")),
    ("price_asc", _lazy("Harga Terendah")),
    ("price_desc", _lazy("Harga Tertinggi")),
    ("name", _lazy("Nama A–Z")),
]
PET_FILTERS = [p for p in PetType.values if p != PetType.ALL]
CONDITION_FILTERS = list(ProductCondition.values)
CATEGORY_BLURB = {
    "MAKANAN": _lazy("Makanan sehat dan lezat"),
    "PERLENGKAPAN": _lazy("Perlengkapan praktis dan awet"),
    "AKSESORIS": _lazy("Aksesori yang lucu dan nyaman"),
    "KESEHATAN": _lazy("Perawatan kesehatan yang terpercaya"),
    "MAINAN": _lazy("Mainan seru"),
}


def _positive_int(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def _picked(request, name, allowed=None):
    """Ambil nilai checkbox ?name=a&name=b (huruf besar, tanpa duplikat, hanya yang valid)."""
    seen = []
    for raw in request.GET.getlist(name):
        code = raw.strip().upper()
        if code and code not in seen and (allowed is None or code in allowed):
            seen.append(code)
    return seen


def _sold_units():
    """Total unit terjual per produk (pesanan yang dibatalkan tidak dihitung)."""
    return Coalesce(
        Sum(
            "orderdetail__quantity",
            filter=~Q(orderdetail__transaction__order_status=OrderStatus.CANCELLED),
        ),
        0,
    )


def _heading(pets, categories, query, has_filters):
    one_pet = PET_LABEL[pets[0]] if len(pets) == 1 else None
    one_cat = categories[0] if len(categories) == 1 else None
    cat_label = CATEGORY_LABELS.get(one_cat, one_cat.title()) if one_cat else None
    if cat_label and one_pet:
        title = f"{cat_label} {one_pet}"
    elif cat_label:
        title = cat_label
    elif one_pet:
        title = _("Produk untuk %(pet)s") % {"pet": one_pet}
    elif query:
        title = _("Hasil pencarian “%(q)s”") % {"q": query}
    elif has_filters:
        title = _("Hasil Filter")
    else:
        title = _("Semua Produk")
    opening = (
        CATEGORY_BLURB.get(one_cat, _("Temukan kebutuhan terbaik"))
        if one_cat
        else _("Temukan kebutuhan terbaik")
    )
    target = (
        _("%(pet)s kesayangan Anda") % {"pet": one_pet.lower()} if one_pet else _("hewan kesayangan Anda")
    )
    return title, _("%(opening)s untuk %(target)s.") % {"opening": opening, "target": target}


def products(request):
    """Daftar produk: filter jenis hewan, kategori, harga, kondisi + urutan."""
    base = Product.objects.sellable().select_related("category")
    all_products = list(base)

    pets = _picked(request, "pet", PET_FILTERS)
    categories = _picked(request, "category")
    conditions = _picked(request, "condition", CONDITION_FILTERS)
    min_price = _positive_int(request.GET.get("min_price"))
    max_price = _positive_int(request.GET.get("max_price"))
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "popular")
    if sort not in dict(SORT_OPTIONS):
        sort = "popular"

    queryset = base
    if pets:
        # Produk "Semua Hewan" cocok dengan jenis hewan apa pun.
        queryset = queryset.filter(Q(pet_type__in=pets) | Q(pet_type=PetType.ALL))
    if categories:
        queryset = queryset.filter(category__name__in=categories)
    if conditions:
        queryset = queryset.filter(condition__in=conditions)
    if min_price is not None:
        queryset = queryset.filter(selling_price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(selling_price__lte=max_price)
    if query:
        queryset = queryset.filter(name__icontains=query)

    if sort == "popular":
        queryset = queryset.annotate(sold=_sold_units()).order_by("-sold", "name")
    elif sort == "newest":
        queryset = queryset.order_by("-created_at", "name")
    elif sort == "price_asc":
        queryset = queryset.order_by("selling_price", "name")
    elif sort == "price_desc":
        queryset = queryset.order_by("-selling_price", "name")
    else:
        queryset = queryset.order_by("name")

    page_obj = Paginator(queryset, PRODUCTS_PER_PAGE).get_page(request.GET.get("page"))

    has_filters = bool(
        pets
        or categories
        or conditions
        or min_price is not None
        or max_price is not None
        or query
    )
    title, blurb = _heading(pets, categories, query, has_filters)

    params = request.GET.copy()
    params.pop("page", None)

    category_options = [
        {**card, "checked": card["code"] in categories}
        for card in _category_cards(all_products)
    ]
    chips = (
        ([f"Pencarian: “{query}”"] if query else [])
        + [PET_LABEL[code] for code in pets]
        + [c["label"] for c in category_options if c["checked"]]
        + [CONDITION_LABEL[code] for code in conditions]
        + (
            [f"Mulai Rp {min_price:,}".replace(",", ".")]
            if min_price is not None
            else []
        )
        + (
            [f"Sampai Rp {max_price:,}".replace(",", ".")]
            if max_price is not None
            else []
        )
    )

    return render(
        request,
        "customer/products.html",
        _site_context(
            active_page="shop",
            query=query,
            title=title,
            blurb=blurb,
            page_obj=page_obj,
            products=page_obj.object_list,
            total=page_obj.paginator.count,
            pet_options=[
                {"code": c, "label": PET_LABEL[c], "checked": c in pets}
                for c in PET_FILTERS
            ],
            category_options=category_options,
            condition_options=[
                {"code": c, "label": CONDITION_LABEL[c], "checked": c in conditions}
                for c in CONDITION_FILTERS
            ],
            min_price=min_price,
            max_price=max_price,
            sort=sort,
            sort_options=SORT_OPTIONS,
            has_filters=has_filters,
            filter_chips=chips,
            query_string=params.urlencode(),
        ),
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.sellable().select_related("category"), pk=pk
    )
    related = (
        Product.objects.sellable()
        .select_related("category")
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by("name")[:4]
    )
    return render(
        request,
        "customer/product_detail.html",
        _site_context(active_page="shop", product=product, related_products=related),
    )


def _is_customer(user):
    return user.is_authenticated and user.role == Role.CUSTOMER


def checkout_page(request):
    """Checkout dipisah: customer yang login memesan langsung ke sistem,
    pengunjung (belum login) tetap memesan lewat WhatsApp admin."""
    if _is_customer(request.user):
        # Isian awal titik peta: titik rumah di akun, atau titik pesanan terakhir.
        last = (request.user.latitude, request.user.longitude) if request.user.has_pin else (
            Order.objects.filter(customer=request.user, delivery_latitude__isnull=False)
            .order_by("-date")
            .values_list("delivery_latitude", "delivery_longitude")
            .first()
        )
        return render(
            request,
            "customer/checkout_member.html",
            _site_context(
                active_page="shop",
                payment_methods=[(m.value, m.label) for m in ONLINE_PAYMENT_METHODS],
                place_url=reverse("customer:place_order"),
                last_pin=last,
            ),
        )
    return render(
        request,
        "customer/checkout.html",
        _site_context(
            active_page="shop",
            next_url=reverse("customer:checkout"),
            wa_number=StoreSettings.current().whatsapp,
        ),
    )


ADDRESS_MAX = 255


def _parse_location(payload):
    """(lat, lng) Decimal dari input pelanggan, atau None bila kosong/tidak valid."""
    from decimal import Decimal, InvalidOperation

    try:
        lat = Decimal(str(payload.get("latitude"))).quantize(Decimal("0.000001"))
        lng = Decimal(str(payload.get("longitude"))).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def shipping_quote(request):
    """Ongkir untuk titik peta yang dipilih pelanggan (dipakai halaman checkout)."""
    location = _parse_location(request.GET)
    if location is None:
        return JsonResponse(
            {"ok": False, "message": _("Tandai lokasi pengiriman di peta.")}, status=400
        )
    store = StoreSettings.current()
    distance = store.distance_km(*location)
    deliverable = store.can_deliver_to(distance)
    return JsonResponse(
        {
            "ok": deliverable,
            "distance_km": round(distance, 2),
            "fee": store.shipping_fee(distance) if deliverable else None,
            "max_km": float(store.max_delivery_km),
            "message": (
                ""
                if deliverable
                else (
                    f"Lokasi berjarak {distance:.1f} km dari toko, di luar jangkauan antar "
                    f"(maks. {store.max_delivery_km} km)."
                )
            ),
        }
    )


@roleRequired(Role.CUSTOMER)
@require_POST
def place_order(request):
    """Buat pesanan online dari keranjang (JSON). Harga & stok dicek di server."""
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return _order_error("Data pesanan tidak bisa dibaca.")
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return _order_error("Keranjang Anda kosong.")
    lines = [
        (item.get("id"), item.get("quantity"))
        for item in items[:100]
        if isinstance(item, dict)
    ]
    address = str(payload.get("address") or "").strip()
    if not address:
        return _order_error("Alamat pengiriman wajib diisi.", field="address")
    if len(address) > ADDRESS_MAX:
        return _order_error(
            "Alamat terlalu panjang (maks. 255 karakter).", field="address"
        )

    location = _parse_location(payload)
    if location is None:
        return _order_error("Tandai titik lokasi pengiriman di peta.", field="location")

    customer = request.user
    if not customer.phone_number:
        return _order_error("Lengkapi nomor telepon di akun Anda terlebih dahulu.")
    expected_total = payload.get("expected_total")
    if expected_total is not None:
        try:
            expected_total = int(expected_total)
        except (TypeError, ValueError):
            return _order_error("Data pesanan tidak bisa dibaca.")
    client_token = str(payload.get("client_token") or "")
    try:
        with transaction.atomic():
            if address != customer.address:
                # Alamat terakhir disimpan di akun sebagai isian berikutnya;
                # order sendiri menyimpan salinan alamatnya (shipping_address).
                customer.address = address
                customer.save(update_fields=["address"])
            if not customer.has_pin:
                customer.latitude, customer.longitude = location
                customer.save(update_fields=["latitude", "longitude"])
            order = Order.place_online(
                customer,
                lines,
                str(payload.get("payment_method") or ""),
                note=str(payload.get("note") or ""),
                address=address,
                client_token=client_token,
                expected_total=expected_total,
                location=location,
            )
    except PriceChanged as error:
        return JsonResponse(
            {
                "ok": False,
                "message": str(error),
                "field": None,
                "reason": "price_changed",
            },
            status=409,
        )
    except PetshopError as error:
        return _order_error(str(error))
    except IntegrityError:
        # Dua kiriman dengan token yang sama tiba bersamaan: pakai order yang menang.
        order = Order.objects.filter(
            customer=customer, client_token=client_token
        ).first()
        if order is None:
            return _order_error("Pesanan gagal dibuat, coba lagi.")
    return JsonResponse(
        {
            "ok": True,
            "order_id": order.pk,
            "tracking_number": order.tracking_number,
            "redirect": f"{reverse('customer:my_orders')}?baru={order.pk}",
        }
    )


def _order_error(message, field=None):
    return JsonResponse({"ok": False, "message": message, "field": field}, status=400)


ACTIVE_ORDER_STATUSES = (
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.ON_DELIVERY,
)


@roleRequired(Role.CUSTOMER)
def dashboard(request):
    """Dasbor pelanggan: pesanan aktif, pembayaran, booking, dan notifikasi dalam satu halaman."""
    from service.models import BookingStatus
    from store.models import Notification

    user = request.user
    Order.cancel_expired()
    orders = (
        Order.objects.filter(customer=user)
        .select_related("courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )
    active = [o for o in orders.filter(order_status__in=ACTIVE_ORDER_STATUSES)]
    for order in active:
        order.steps = _tracking_steps(order)
    unpaid = [
        o
        for o in active
        if o.payment_method == "TRANSFER" and o.payment_status == "MENUNGGU"
    ]
    bookings = user.service_bookings.select_related("service", "groomer")
    upcoming = list(
        bookings.exclude(
            status__in=[
                BookingStatus.DONE,
                BookingStatus.CANCELLED,
                BookingStatus.NO_SHOW,
            ]
        ).order_by("schedule")[:5]
    )
    reminder_days = StoreSettings.current().grooming_reminder_days
    pets = list(user.pets.filter(is_active=True)[:6])
    for pet in pets:
        pet.last = pet.last_service()
        pet.due = pet.grooming_due(reminder_days)
    history = list(
        orders.filter(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED])[
            :5
        ]
    )
    spent = (
        orders.filter(payment_status="LUNAS")
        .exclude(order_status=OrderStatus.CANCELLED)
        .aggregate(total=Sum("total_payment"))["total"]
        or 0
    )
    notifications = list(Notification.objects.filter(user=user)[:5])
    live = [o for o in active if o.order_status == OrderStatus.ON_DELIVERY]
    return render(
        request,
        "customer/dashboard.html",
        _site_context(
            active_page="dashboard",
            active_orders=active,
            live_orders=live,
            unpaid_orders=unpaid,
            upcoming_bookings=upcoming,
            pets=pets,
            history=history,
            notifications=notifications,
            stats={
                "active": len(active),
                "unpaid": len(unpaid),
                "bookings": len(upcoming),
                "spent": spent,
            },
        ),
    )


@roleRequired(Role.CUSTOMER)
@require_POST
def rate_order(request, pk):
    """Pelanggan memberi bintang 1-5 + ulasan setelah pesanan sampai."""
    from service.forms import RatingForm
    from store.models import Notification

    order = get_object_or_404(Order, pk=pk, customer=request.user)
    form = RatingForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Pilih jumlah bintang terlebih dahulu."))
        return redirect("customer:my_orders")
    try:
        order.rate(
            request.user, form.cleaned_data["stars"], form.cleaned_data["review"]
        )
    except InvalidTransition as e:
        messages.error(request, str(e))
    else:
        if order.courier_id:
            Notification.send(
                order.courier,
                f"Ulasan {order.rating}★ untuk pesanan #{order.pk}",
                order.review,
            )
        messages.success(request, _("Terima kasih atas ulasannya!"))
    return redirect("customer:my_orders")


@roleRequired(Role.CUSTOMER)
def account(request):
    """Profil pelanggan: ubah data diri & kata sandi."""
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.forms import PasswordChangeForm

    from account.form import ProfilePhotoForm, ProfileForm

    user = Customer.objects.get(pk=request.user.pk)
    profile_form = ProfileForm(instance=user)
    password_form = PasswordChangeForm(request.user)
    photo_form = ProfilePhotoForm()
    if request.method == "POST":
        if request.POST.get("form") == "photo":
            photo_form = ProfilePhotoForm(request.POST, request.FILES)
            if photo_form.is_valid():
                photo_form.save(user)
                messages.success(
                    request, _("Foto profil dihapus.") if not user.photo else _("Foto profil diperbarui.")
                )
                return redirect("customer:account")
            for error in photo_form.errors.values():
                messages.error(request, " ".join(error))
            return redirect("customer:account")
        if request.POST.get("form") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, _("Kata sandi berhasil diganti."))
                return redirect("customer:account")
        else:
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, _("Profil berhasil diperbarui."))
                return redirect("customer:account")
    for field in password_form.fields.values():
        field.widget.attrs["class"] = "form-control"
    for field in profile_form.fields.values():
        field.widget.attrs["class"] = "form-control"
    orders = Order.objects.filter(customer=user)
    stats = {
        "orders": orders.count(),
        "active": orders.filter(
            order_status__in=[
                OrderStatus.PENDING,
                OrderStatus.CONFIRMED,
                OrderStatus.ON_DELIVERY,
            ]
        ).count(),
        "bookings": user.service_bookings.count(),
    }
    return render(
        request,
        "customer/account.html",
        _site_context(
            active_page="account",
            profile_form=profile_form,
            password_form=password_form,
            stats=stats,
        ),
    )


@roleRequired(Role.CUSTOMER)
def my_orders(request):
    Order.cancel_expired()
    # Pembayaran layanan saja (tanpa barang) tampil di Booking Saya, bukan di sini.
    orders = (
        Order.objects.filter(customer=request.user)
        .exclude(
            pk__in=Order.objects.filter(
                customer=request.user, details__isnull=True, service_lines__isnull=False
            ).values("pk")
        )
        .select_related("courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )
    new_id = request.GET.get("baru", "")
    new_order = orders.filter(pk=int(new_id)).first() if new_id.isdigit() else None
    # Tab penyaring: kelompok status yang mudah dipahami pelanggan.
    running = (OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.ON_DELIVERY)
    groups = {
        "berjalan": Q(order_status__in=running),
        "bayar": Q(payment_method="TRANSFER", payment_status="MENUNGGU")
        & ~Q(order_status=OrderStatus.CANCELLED),
        "selesai": Q(order_status=OrderStatus.DELIVERED),
        "batal": Q(order_status=OrderStatus.CANCELLED),
    }
    tab = request.GET.get("tab", "")
    if tab not in groups:
        tab = ""
    tabs = [("", _("Semua"), orders.count())] + [
        (key, label, orders.filter(groups[key]).count())
        for key, label in (
            ("berjalan", _("Berjalan")),
            ("bayar", _("Perlu dibayar")),
            ("selesai", _("Selesai")),
            ("batal", _("Dibatalkan")),
        )
    ]
    shown = orders.filter(groups[tab]) if tab else orders
    return render(
        request,
        "customer/my_orders.html",
        _site_context(
            active_page="orders",
            orders=shown,
            new_order=new_order,
            tab=tab,
            tabs=tabs,
        ),
    )


@roleRequired(Role.CUSTOMER)
def payment_proof(request, pk):
    """Pelanggan memotret bukti transfer (kamera web) atau memilih tangkapan layar m-banking."""
    from store.models import ActivityLog, Notification

    from .forms import PaymentProofForm

    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if not order.can_upload_proof:
        messages.info(
            request, f"Pesanan #{order.pk} tidak sedang menunggu bukti transfer."
        )
        return redirect("customer:dashboard")
    form = PaymentProofForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            order.submit_payment_proof(request.user, form.cleaned_data["photo"])
        except PetshopError as error:
            messages.error(request, str(error))
        else:
            ActivityLog.record(order, "Bukti transfer dikirim", actor=request.user)
            Notification.to_staff(
                [Role.SUPERADMIN, Role.ADMIN, Role.CASHIER],
                f"Bukti transfer pesanan #{order.pk}",
                f"{request.user.name} mengirim bukti Rp {order.total_payment:,}".replace(
                    ",", "."
                ),
                reverse("transaction:payment_check", args=[order.pk]),
            )
            messages.success(
                request,
                _("Bukti transfer terkirim. Kami kabari begitu pembayaran dicek."),
            )
            return redirect("customer:dashboard")
    return render(
        request,
        "customer/payment_proof.html",
        _site_context(active_page="dashboard", order=order, form=form),
    )


@roleRequired(Role.CUSTOMER)
def handover_qr(request, pk):
    """QR serah-terima: hanya pemilik pesanan yang bisa melihat, discan kurir saat paket diserahkan."""
    from transaction.qr import qr_response

    order = get_object_or_404(Order, pk=pk, customer=request.user)
    return qr_response(order.handover_payload)


def track_handover_qr(request, resi):
    """QR serah-terima lewat tautan berkunci (dikirim kasir ke WhatsApp pembeli)."""
    from transaction.qr import qr_response

    order = get_object_or_404(Order, tracking_number=normalize_tracking_number(resi) or "-")
    if not (order.shows_handover_qr and order.check_handover_key(request.GET.get("k"))):
        raise Http404
    response = qr_response(order.handover_payload)
    response["Cache-Control"] = "private, no-store"
    return response


def tracking_qr(request, resi):
    """QR berisi nomor resi (untuk label paket & halaman lacak)."""
    from transaction.qr import qr_response

    code = normalize_tracking_number(resi)
    if not code:
        return JsonResponse({"found": False}, status=404)
    return qr_response(code)


@roleRequired(Role.CUSTOMER)
@require_POST
def cancel_my_order(request, pk):
    try:
        with transaction.atomic():
            # Kunci baris dulu: status dicek ulang setelah admin mungkin baru
            # saja mengonfirmasi pesanan yang sama.
            order = get_object_or_404(
                Order.objects.select_for_update(), pk=pk, customer=request.user
            )
            order.cancel_by_customer(request.user)
    except PetshopError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Pesanan #{order.pk} dibatalkan.")
    return redirect("customer:my_orders")


def _mask_name(name):
    """'Budi Santoso' -> 'Budi S****' (halaman lacak bisa dibuka siapa pun yang punya resi)."""
    parts = (name or "").split()
    if not parts:
        return ""
    return " ".join(
        [parts[0]] + [f"{p[0]}{'*' * min(len(p) - 1, 4)}" for p in parts[1:]]
    )


def _tracking_steps(order):
    """Linimasa status pesanan; langkah terakhir yang selesai = posisi pesanan sekarang."""
    if order.is_online:
        # Pesanan dari situs: dibuat pelanggan dulu, lalu dikonfirmasi toko.
        steps = [
            {
                "icon": "fa-cart-shopping",
                "title": _("Pesanan dibuat"),
                "time": order.date,
                "done": True,
            },
            {
                "icon": "fa-clipboard-check",
                "title": (
                    _("Dikonfirmasi toko")
                    if order.order_status != OrderStatus.PENDING
                    else _("Menunggu konfirmasi toko")
                ),
                "time": order.confirmed_at,
                "done": order.order_status
                not in (OrderStatus.PENDING, OrderStatus.CANCELLED),
            },
        ]
    else:
        steps = [
            {
                "icon": "fa-clipboard-check",
                "title": _("Pesanan dikonfirmasi"),
                "time": order.date,
                "done": True,
            },
        ]
    steps += [
        {
            "icon": "fa-truck-fast",
            "title": _("Sedang dikirim kurir"),
            "time": order.shipped_at,
            "done": order.order_status
            in (OrderStatus.ON_DELIVERY, OrderStatus.DELIVERED),
        },
        {
            "icon": "fa-box-open",
            "title": _("Pesanan sampai"),
            "time": order.delivered_at,
            "done": order.order_status == OrderStatus.DELIVERED,
        },
    ]
    current = max((i for i, step in enumerate(steps) if step["done"]), default=0)
    for i, step in enumerate(steps):
        step["current"] = i == current
    return steps


TRACK_MAX_FAILURES = 5
TRACK_LOCK_SECONDS = 15 * 60
TRACK_SESSION_KEY = "track_ok"


def _track_allowed(request, order):
    """Detail lacak terbuka untuk pemilik yang login, staf, atau pengunjung yang sudah verifikasi."""
    user = request.user
    if user.is_authenticated and (order.customer_id == user.pk or user.role != Role.CUSTOMER):
        return True
    return order.pk in request.session.get(TRACK_SESSION_KEY, [])


def _track_grant(request, order):
    granted = [pk for pk in request.session.get(TRACK_SESSION_KEY, []) if pk != order.pk]
    request.session[TRACK_SESSION_KEY] = (granted + [order.pk])[-20:]


def _track_verify(request, order):
    """Pengunjung tanpa login mengetik 4 digit terakhir nomor WA pemesan. Mengembalikan pesan galat."""
    from django.core.cache import cache

    throttle = f"track-fail:{order.pk}:{request.META.get('REMOTE_ADDR', '')}"
    failures = cache.get(throttle, 0)
    if failures >= TRACK_MAX_FAILURES:
        return _("Terlalu banyak percobaan. Coba lagi dalam 15 menit atau hubungi toko.")
    digits = "".join(ch for ch in request.POST.get("wa4", "") if ch.isdigit())
    expected = order.phone_last4
    if len(digits) == 4 and expected and secrets.compare_digest(digits, expected):
        cache.delete(throttle)
        _track_grant(request, order)
        return ""
    cache.set(throttle, failures + 1, TRACK_LOCK_SECONDS)
    return _("4 digit nomor WhatsApp tidak cocok dengan data pemesan.")


def track_order(request, resi=None):
    """Lacak pesanan lewat nomor resi: ?resi=... (form) atau /lacak/<resi>/ (tautan).

    Resi tertera di label paket, jadi pengunjung tanpa login wajib memasukkan 4 digit
    terakhir nomor WhatsApp pemesan sebelum status, isi paket, dan peta ditampilkan.
    """
    raw = (resi if resi is not None else request.GET.get("resi", "")).strip()
    order = None
    error = ""
    if raw:
        code = normalize_tracking_number(raw)
        if code:
            order = (
                Order.objects.select_related("customer", "courier")
                .prefetch_related("details__product")
                .filter(tracking_number=code)
                .first()
            )
        if order is None:
            error = "Resi tidak ditemukan. Periksa kembali nomor resi Anda (contoh: PS-261022-K7M2QX)."
    context = {"raw": raw, "error": error, "order": None}
    if order is not None and order.check_handover_key(request.GET.get("k", "")):
        _track_grant(request, order)  # tautan dari kasir ke WA pembeli sudah terverifikasi
    if order is not None and not _track_allowed(request, order):
        verify_error = ""
        if request.method == "POST":
            verify_error = _track_verify(request, order)
            if not verify_error:
                return redirect("customer:track_detail", resi=order.tracking_number)
        context.update(
            locked=order.tracking_number, verify_error=verify_error,
            login_url=reverse("login_form") + "?next=" + reverse("customer:track_detail", args=[order.tracking_number]),
        )
        order = None
    if order is not None:
        context.update(
            order=order,
            steps=_tracking_steps(order),
            masked_name=_mask_name(order.customer.name),
            courier_name=(
                (order.courier.get_full_name() or order.courier.username)
                if order.courier
                else ""
            ),
            courier_photo=order.courier.photo_url if order.courier else "",
            items=list(order.details.all()),
        )
        # QR serah-terima: untuk pemilik yang login, atau tautan berkunci dari kasir (pembeli tanpa login).
        key = request.GET.get("k", "")
        if order.shows_handover_qr:
            if order.check_handover_key(key):
                context["handover_qr_url"] = reverse("customer:track_handover_qr", args=[order.tracking_number]) + "?k=" + key
            elif request.user.is_authenticated and order.customer_id == request.user.pk:
                context["handover_qr_url"] = reverse("customer:handover_qr", args=[order.pk])
    response = render(
        request,
        "customer/track.html",
        _site_context(active_page="track", **context),
    )
    # Halaman ini memuat foto bukti: jangan disimpan cache bersama.
    response["Cache-Control"] = "private, no-store"
    return response


LIVE_STALE_AFTER = timedelta(minutes=3)
LIVE_POLL_SECONDS = 10


def _live_destination(request, order, last):
    """Titik tujuan, jarak, ETA & urutan antar; hanya untuk pemilik pesanan (alamat tidak dibuka ke umum)."""
    is_owner = request.user.is_authenticated and order.customer_id == request.user.pk
    if not is_owner or not order.has_pin:
        return {}
    from courier.routing import eta_minutes, path_length

    info = {
        "destination": {
            "lat": float(order.delivery_latitude),
            "lng": float(order.delivery_longitude),
        }
    }
    stops = order.stops_before()
    if stops is not None:
        info["stops_before"] = stops
    if last:
        # Jarak lewat alamat-alamat yang dikunjungi lebih dulu, bukan garis lurus ke rumah.
        earlier = Order.objects.filter(
            courier_id=order.courier_id,
            order_status=OrderStatus.ON_DELIVERY,
            route_position__lt=order.route_position or 0,
            delivery_latitude__isnull=False,
        ).order_by("route_position")
        points = [
            (float(o.delivery_latitude), float(o.delivery_longitude)) for o in earlier
        ]
        points.append((float(order.delivery_latitude), float(order.delivery_longitude)))
        km = path_length((last["lat"], last["lng"]), points)
        info["distance_km"] = round(km, 2)
        info["eta_minutes"] = eta_minutes(km, len(points) - 1)
    return info


@never_cache
def track_location(request, resi):
    """Peta lacak (JSON): toko & alamat sejak pesanan dibuat, posisi kurir selama paket diantar."""
    code = normalize_tracking_number(resi)
    order = (
        Order.objects.select_related("courier").filter(tracking_number=code).first()
        if code
        else None
    )
    if order is None:
        return JsonResponse({"found": False}, status=404)
    if not _track_allowed(request, order):
        return JsonResponse({"found": True, "locked": True}, status=403)
    data = {
        "found": True,
        "status": order.order_status,
        "live": False,
        "points": [],
        "last": None,
        "stale": False,
        "poll": LIVE_POLL_SECONDS,
    }
    # Peta tampil sejak pesanan dibuat (toko -> alamat); posisi kurir masuk begitu paket diantar.
    if order.order_status in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
        store = StoreSettings.current()
        data["store"] = {
            "lat": float(store.latitude),
            "lng": float(store.longitude),
            "name": store.name,
        }
        data.update(_live_destination(request, order, None))
    elif order.order_status == OrderStatus.ON_DELIVERY:
        trail = CourierLocation.trail_for(order)
        if trail:
            last = trail[-1]
            data.update(
                live=True,
                points=[[float(p.latitude), float(p.longitude)] for p in trail],
                last=last.as_point(),
                stale=timezone.now() - last.recorded_at > LIVE_STALE_AFTER,
            )
        store = StoreSettings.current()
        data["store"] = {
            "lat": float(store.latitude),
            "lng": float(store.longitude),
            "name": store.name,
        }
        data.update(_live_destination(request, order, data["last"]))
    response = JsonResponse(data)
    response["Cache-Control"] = "private, no-store"
    return response
