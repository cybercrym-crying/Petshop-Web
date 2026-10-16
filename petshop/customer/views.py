import json
import urllib.parse

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from account.models import Customer
from account.phone import normalize_phone
from product.models import Category, Product

PAGE_SIZE = 12
MAX_ADDRESS_LENGTH = 255

PAYMENT_METHODS = ("Cash on Delivery (COD)", "Bank Transfer", "E-Wallet")

CATEGORY_IMAGES = {
    Category.FOOD: "customer/img/pet-food.png",
    Category.EQUIPMENT: "customer/img/pet-toys.png",
    Category.ACCESSORIES: "customer/img/pet-accessories.png",
}

SORT_OPTIONS = {
    "newest": ("Newest", "-created_at"),
    "price_asc": ("Price: low to high", "selling_price"),
    "price_desc": ("Price: high to low", "-selling_price"),
    "name": ("Name: A to Z", "name"),
}


def _format_rupiah(amount):
    return f"Rp {int(amount):,}".replace(",", ".")


def _parse_positive_int(value):
    """Return a non-negative int, or None when the value is missing or invalid."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _category_options():
    """Categories shown on the home page and in the shop filter, with product counts."""
    counts = dict(
        Product.objects.sellable()
        .values_list("category__name")
        .annotate(total=Count("pk"))
    )
    return [
        {
            "code": code,
            "label": label,
            "image": CATEGORY_IMAGES.get(code, "customer/img/product-placeholder.svg"),
            "count": counts.get(code, 0),
        }
        for code, label in Category.CATEGORY_CHOICES
    ]


def home(request):
    return render(request, "customer/home.html", {"active_page": "home"})


POPULAR_PRODUCT_COUNT = 8


def home_shop(request):
    popular = (
        Product.objects.sellable()
        .select_related("category")
        .order_by("-created_at")[:POPULAR_PRODUCT_COUNT]
    )
    context = {
        "active_page": "shop",
        "categories": _category_options(),
        "popular_products": popular,
    }
    return render(request, "customer/home_shop.html", context)


def shop(request):
    products = Product.objects.sellable().select_related("category")
    categories = _category_options()
    valid_codes = {category["code"] for category in categories}

    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(name__icontains=query)

    selected_categories = [
        code for code in request.GET.getlist("category") if code in valid_codes
    ]
    if selected_categories:
        products = products.filter(category__name__in=selected_categories)

    min_price = _parse_positive_int(request.GET.get("min_price"))
    max_price = _parse_positive_int(request.GET.get("max_price"))
    if min_price is not None:
        products = products.filter(selling_price__gte=min_price)
    if max_price is not None:
        products = products.filter(selling_price__lte=max_price)

    in_stock_only = request.GET.get("in_stock") == "1"
    if in_stock_only:
        products = products.filter(stock__gt=0)

    sort = request.GET.get("sort", "newest")
    if sort not in SORT_OPTIONS:
        sort = "newest"
    products = products.order_by(SORT_OPTIONS[sort][1], "pk")

    # The wishlist is stored in the browser, so the page lists everything and
    # shop.js hides the products that are not in the wishlist.
    wishlist_mode = request.GET.get("wishlist") == "1"

    if wishlist_mode:
        page_obj = None
        product_list = products
        title = "My Wishlist"
    else:
        page_obj = Paginator(products, PAGE_SIZE).get_page(request.GET.get("page"))
        product_list = page_obj.object_list
        if query:
            title = f"Results for “{query}”"
        elif len(selected_categories) == 1:
            title = next(
                c["label"] for c in categories if c["code"] == selected_categories[0]
            )
        else:
            title = "All Products"

    params = request.GET.copy()
    params.pop("page", None)

    context = {
        "active_page": "shop",
        "title": title,
        "products": product_list,
        "page_obj": page_obj,
        "categories": categories,
        "selected_categories": selected_categories,
        "query": query,
        "min_price": min_price,
        "max_price": max_price,
        "in_stock_only": in_stock_only,
        "sort": sort,
        "sort_options": [(key, label) for key, (label, _) in SORT_OPTIONS.items()],
        "wishlist_mode": wishlist_mode,
        "query_string": params.urlencode(),
        "has_filters": bool(
            query
            or selected_categories
            or min_price is not None
            or max_price is not None
            or in_stock_only
        ),
    }
    return render(request, "customer/shop.html", context)


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.sellable().select_related("category"), pk=pk
    )
    related = (
        Product.objects.sellable()
        .select_related("category")
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by("-created_at")[:3]
    )
    context = {
        "active_page": "shop",
        "product": product,
        "related_products": related,
    }
    return render(request, "customer/product_detail.html", context)


def cart_page(request):
    return render(request, "customer/cart.html", {"active_page": "cart"})


def checkout_page(request):
    context = {"active_page": "cart", "payment_methods": PAYMENT_METHODS}
    return render(request, "customer/checkout.html", context)


def _read_cart_quantities(raw_cart):
    """Turn the cart JSON sent by the browser into {product_id: quantity}."""
    try:
        entries = json.loads(raw_cart or "[]")
    except json.JSONDecodeError:
        return {}
    if not isinstance(entries, list):
        return {}

    quantities = {}
    for entry in entries:
        try:
            product_id = int(entry["id"])
            quantity = int(entry["quantity"])
        except (KeyError, TypeError, ValueError):
            continue
        if quantity > 0:
            quantities[product_id] = quantities.get(product_id, 0) + quantity
    return quantities


def _build_whatsapp_message(name, phone, address, payment_method, note, lines):
    total = sum(product.selling_price * quantity for product, quantity in lines)
    message = (
        "Hello, I would like to place an order.\n\n"
        "*Order Details*\n"
        f"• Full Name: {name}\n"
        f"• Phone / WhatsApp: {phone}\n"
        f"• Address: {address}\n"
        f"• Payment Method: {payment_method}\n\n"
        "*Order Summary*\n"
    )
    for product, quantity in lines:
        unit = _format_rupiah(product.selling_price)
        subtotal = _format_rupiah(product.selling_price * quantity)
        message += f"- {product.name} - {quantity}x ({unit}) = {subtotal}\n"
    message += f"\n*Estimated total (excl. shipping): {_format_rupiah(total)}*\n"
    if note:
        message += f"\n*Note:* {note}\n"
    message += "\nPlease let me know the total including shipping. Thank you!"
    return message


@require_POST
def place_order(request):
    """Validate the checkout form and return the WhatsApp link for the order.

    Prices and stock always come from the database, never from the browser.
    """
    errors = {}

    name = request.POST.get("name", "").strip()
    raw_phone = request.POST.get("phone", "")
    address = request.POST.get("address", "").strip()
    note = request.POST.get("note", "").strip()
    payment_method = request.POST.get("payment_method", "")

    if not name:
        errors["name"] = "Please enter your full name."

    phone = ""
    try:
        phone = normalize_phone(raw_phone)
    except ValueError:
        errors["phone"] = "Please enter a valid phone number, e.g. 081234567890."

    if not address:
        errors["address"] = "Please enter your delivery address."
    elif len(address) > MAX_ADDRESS_LENGTH:
        errors["address"] = f"Address must be at most {MAX_ADDRESS_LENGTH} characters."

    if payment_method not in PAYMENT_METHODS:
        errors["payment_method"] = "Please choose a payment method."

    quantities = _read_cart_quantities(request.POST.get("cart_data"))
    available = Product.objects.sellable().in_bulk(list(quantities))
    lines = []
    for product_id, quantity in quantities.items():
        product = available.get(product_id)
        if product is None:
            errors["cart"] = (
                "Some items in your cart are no longer available. "
                "Please review your cart."
            )
        elif quantity > product.stock:
            errors["cart"] = (
                f"Only {product.stock} left of “{product.name}”. "
                "Please update your cart."
            )
        else:
            lines.append((product, quantity))
    if not quantities:
        errors["cart"] = "Your cart is empty."

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    Customer.objects.get_or_create(
        phone_number=phone,
        defaults={"name": name, "address": address},
    )

    message = _build_whatsapp_message(
        name, phone, address, payment_method, note, lines
    )
    admin_number = getattr(settings, "WHATSAPP_ADMIN_NUMBER", "6281356703075")
    whatsapp_url = f"https://wa.me/{admin_number}?text={urllib.parse.quote(message)}"
    return JsonResponse({"ok": True, "whatsapp_url": whatsapp_url})

