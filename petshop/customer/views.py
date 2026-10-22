from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from product.models import PetType, Product, ProductCondition
from account.models import Customer
from transaction.models import Order, OrderStatus

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
    "PERLENGKAPAN": "customer/img/pet-toys.png",
    "AKSESORIS": "customer/img/pet-accessories.png",
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


def checkout_page(request):
    return render(request, "customer/checkout.html")
