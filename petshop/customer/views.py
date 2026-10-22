import json
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.http import require_POST
from django.http import JsonResponse
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
from transaction.models import (
    Order,
    OrderStatus,
    PaymentMethod,
    normalize_tracking_number,
)

from .templatetags.customer_extras import CONDITION_LABEL, CATEGORY_LABELS, PET_LABEL

# Nomor WhatsApp admin (format internasional tanpa +), dipakai tombol kontak dan pesanan.
ADMIN_WA_NUMBER = "6281356703075"
WA_LINK = f"https://wa.me/{ADMIN_WA_NUMBER}"
WA_DISPLAY = "+62 813-5670-3075"


SPECIAL_OFFER = {
    "title": "Diskon 20% untuk Produk Pilihan",
    "text": "Merek premium, barang favorit hewan kesayangan Anda, dengan harga spesial!",
}
STORE_ADDRESS = ""


def _site_context(**extra):
    return {"wa_link": WA_LINK, "wa_display": WA_DISPLAY, **extra}


def home(request):
    return render(request, "customer/home.html", _site_context(offer=SPECIAL_OFFER))


def about(request):
    stats = {
        "products": Product.objects.sellable().count(),
        "orders": Order.objects.filter(order_status=OrderStatus.DELIVERED).count(),
        "customers": Customer.objects.count(),
    }
    return render(
        request,
        "customer/about.html",
        _site_context(stats=stats, store_address=STORE_ADDRESS),
    )


def cart_page(request):
    return render(request, "customer/cart.html")


# Kategori di halaman Belanja: kode (sama dengan Category.name di database) -> gambar.
CATEGORY_IMAGES = {
    "MAKANAN": "customer/img/pet-food.png",
    "PERLENGKAPAN": "customer/img/equipment-pets.png",
    "AKSESORIS": "customer/img/pet-accessories.png",
    "KESEHATAN": "customer/img/healtcare-cat.png",
    "MAINAN": "customer/img/pet-toys.png",
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


PRODUCTS_PER_PAGE = 12
SORT_OPTIONS = [
    ("popular", "Terpopuler"),
    ("newest", "Terbaru"),
    ("price_asc", "Harga Terendah"),
    ("price_desc", "Harga Tertinggi"),
    ("name", "Nama A–Z"),
]
PET_FILTERS = [p for p in PetType.values if p != PetType.ALL]
CONDITION_FILTERS = list(ProductCondition.values)
CATEGORY_BLURB = {
    "MAKANAN": "Makanan sehat dan lezat",
    "PERLENGKAPAN": "Perlengkapan praktis dan awet",
    "AKSESORIS": "Aksesori yang lucu dan nyaman",
    "KESEHATAN": "Perawatan kesehatan yang terpercaya",
    "MAINAN": "Mainan seru",
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
        title = f"Produk untuk {one_pet}"
    elif query:
        title = f"Hasil pencarian “{query}”"
    elif has_filters:
        title = "Hasil Filter"
    else:
        title = "Semua Produk"
    opening = (
        CATEGORY_BLURB.get(one_cat, "Temukan kebutuhan terbaik")
        if one_cat
        else "Temukan kebutuhan terbaik"
    )
    target = (
        f"{one_pet.lower()} kesayangan Anda" if one_pet else "hewan kesayangan Anda"
    )
    return title, f"{opening} untuk {target}."


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
        return render(
            request,
            "customer/checkout_member.html",
            _site_context(
                active_page="shop",
                payment_methods=PaymentMethod.choices,
                place_url=reverse("customer:place_order"),
            ),
        )
    return render(
        request,
        "customer/checkout.html",
        {"next_url": reverse("customer:checkout")},
    )


ADDRESS_MAX = 255


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
        return _order_error("Alamat terlalu panjang (maks. 255 karakter).", field="address")

    customer = request.user
    if not customer.phone_number:
        return _order_error("Lengkapi nomor telepon di akun Anda terlebih dahulu.")
    try:
        with transaction.atomic():
            if address != customer.address:
                # Alamat pengiriman = alamat akun (dipakai kurir & admin).
                customer.address = address
                customer.save(update_fields=["address"])
            order = Order.place_online(
                customer,
                lines,
                str(payload.get("payment_method") or ""),
                note=str(payload.get("note") or ""),
            )
    except PetshopError as error:
        return _order_error(str(error))
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


@roleRequired(Role.CUSTOMER)
def my_orders(request):
    orders = (
        Order.objects.filter(customer=request.user)
        .select_related("courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )
    new_id = request.GET.get("baru", "")
    new_order = (
        orders.filter(pk=int(new_id)).first() if new_id.isdigit() else None
    )
    return render(
        request,
        "customer/my_orders.html",
        _site_context(
            active_page="orders",
            orders=orders,
            new_order=new_order,
        ),
    )


@roleRequired(Role.CUSTOMER)
@require_POST
def cancel_my_order(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    try:
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
    return " ".join([parts[0]] + [f"{p[0]}{'*' * min(len(p) - 1, 4)}" for p in parts[1:]])


def _tracking_steps(order):
    """Linimasa status pesanan; langkah terakhir yang selesai = posisi pesanan sekarang."""
    if order.is_online:
        # Pesanan dari situs: dibuat pelanggan dulu, lalu dikonfirmasi toko.
        steps = [
            {
                "icon": "fa-cart-shopping",
                "title": "Pesanan dibuat",
                "time": order.date,
                "done": True,
            },
            {
                "icon": "fa-clipboard-check",
                "title": "Dikonfirmasi toko"
                if order.order_status != OrderStatus.PENDING
                else "Menunggu konfirmasi toko",
                "time": order.confirmed_at,
                "done": order.order_status
                not in (OrderStatus.PENDING, OrderStatus.CANCELLED),
            },
        ]
    else:
        steps = [
            {
                "icon": "fa-clipboard-check",
                "title": "Pesanan dikonfirmasi",
                "time": order.date,
                "done": True,
            },
        ]
    steps += [
        {
            "icon": "fa-truck-fast",
            "title": "Sedang dikirim kurir",
            "time": order.shipped_at,
            "done": order.order_status
            in (OrderStatus.ON_DELIVERY, OrderStatus.DELIVERED),
        },
        {
            "icon": "fa-box-open",
            "title": "Pesanan sampai",
            "time": order.delivered_at,
            "done": order.order_status == OrderStatus.DELIVERED,
        },
    ]
    current = max((i for i, step in enumerate(steps) if step["done"]), default=0)
    for i, step in enumerate(steps):
        step["current"] = i == current
    return steps


def track_order(request, resi=None):
    """Lacak pesanan lewat nomor resi: ?resi=... (form) atau /lacak/<resi>/ (tautan)."""
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
    if order is not None:
        context.update(
            order=order,
            steps=_tracking_steps(order),
            masked_name=_mask_name(order.customer.name),
            courier_name=(order.courier.get_full_name() or order.courier.username)
            if order.courier
            else "",
            items=list(order.details.all()),
        )
    response = render(
        request,
        "customer/track.html",
        _site_context(active_page="track", **context),
    )
    # Halaman ini memuat foto bukti: jangan disimpan cache bersama.
    response["Cache-Control"] = "private, no-store"
    return response


LIVE_STALE_AFTER = timedelta(minutes=3)
LIVE_POLL_SECONDS = 15


@never_cache
def track_location(request, resi):
    """Posisi kurir (JSON) untuk peta di halaman lacak; hanya selama paket diantar."""
    code = normalize_tracking_number(resi)
    order = (
        Order.objects.select_related("courier").filter(tracking_number=code).first()
        if code
        else None
    )
    if order is None:
        return JsonResponse({"found": False}, status=404)
    data = {
        "found": True,
        "status": order.order_status,
        "live": False,
        "points": [],
        "last": None,
        "stale": False,
        "poll": LIVE_POLL_SECONDS,
    }
    if order.order_status == OrderStatus.ON_DELIVERY:
        trail = CourierLocation.trail_for(order)
        if trail:
            last = trail[-1]
            data.update(
                live=True,
                points=[[float(p.latitude), float(p.longitude)] for p in trail],
                last=last.as_point(),
                stale=timezone.now() - last.recorded_at > LIVE_STALE_AFTER,
            )
    response = JsonResponse(data)
    response["Cache-Control"] = "private, no-store"
    return response
