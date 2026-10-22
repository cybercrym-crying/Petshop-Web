from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import ProtectedError
from .models import (
    Category,
    InsufficientStock,
    LOW_STOCK_THRESHOLD,
    PetType,
    Product,
    ProductCondition,
    StockMutation,
)
from .form import FormProduct, StockMutationForm, SellingPriceForm
from account.models import Role
from account.decorators import roleRequired


def _flash_form_errors(request, form):
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else field
        for error in errors:
            messages.error(request, f"{label}: {error}")


@roleRequired(Role.ADMIN)
def manage_product(request):
    products = Product.objects.select_related("category").order_by("name")
    category = request.GET.get("category")
    q = request.GET.get("q")
    if category and category.isdigit():
        products = products.filter(category_id=category)
    if q:
        products = products.filter(name__icontains=q)
    return render(
        request,
        "product/manage_product.html",
        {
            "products": products,
            "categories": Category.objects.all(),
            "pet_types": PetType.choices,
            "conditions": ProductCondition.choices,
        },
    )


@roleRequired(Role.ADMIN)
def add_product(request):
    if request.method == "POST":
        form = FormProduct(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                product = form.save()
                product.record_initial_stock(user=request.user)
            messages.success(request, f"Produk '{product.name}' berhasil ditambahkan.")
        else:
            _flash_form_errors(request, form)
    return redirect("product:manage_product")


@roleRequired(Role.ADMIN)
def product_list(request):
    q = request.GET.get("q", "").strip()
    active_filter = request.GET.get("filter", "")

    base = Product.objects.select_related("category").order_by("name")
    low = base.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)
    empty = base.filter(stock=0)
    no_price = base.filter(selling_price__isnull=True)
    counts = {
        "all": base.count(),
        "low": low.count(),
        "empty": empty.count(),
        "noprice": no_price.count(),
    }

    queryset = {"low": low, "empty": empty, "noprice": no_price}.get(active_filter, base)
    if active_filter not in ("low", "empty", "noprice"):
        active_filter = ""
    if q:
        queryset = queryset.filter(name__icontains=q)

    products = list(queryset)

    recentMutations = StockMutation.objects.select_related(
        "product", "createdBy"
    ).order_by("-date", "-pk")[:20]
    return render(
        request,
        "product/product_list.html",
        {
            "productList": products,
            "recentMutations": recentMutations,
            "counts": counts,
            "restock_needed": counts["low"] + counts["empty"],
            "active_filter": active_filter,
            "q": q,
            "low_threshold": LOW_STOCK_THRESHOLD,
        },
    )


@roleRequired(Role.ADMIN)
def set_selling_price(request, productId):
    product = get_object_or_404(Product, id=productId)
    if request.method == "POST":
        form = SellingPriceForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Harga jual '{product.name}' berhasil diperbarui."
            )
            return redirect("product:product_list")
    else:
        form = SellingPriceForm(instance=product)
    return render(request, "product/set_price.html", {"form": form, "product": product})


@roleRequired(Role.ADMIN)
def add_stock_mutation(request):
    if request.method == "POST":
        form = StockMutationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                data["product"].apply_mutation(
                    data["mutationType"],
                    data["quantity"],
                    user=request.user,
                    note=data["note"],
                )
            except InsufficientStock as e:
                form.add_error(None, str(e))
            else:
                messages.success(request, "Mutasi stok berhasil dicatat.")
                return redirect("product:product_list")
    else:
        form = StockMutationForm(initial={"product": request.GET.get("product")})
    return render(request, "product/add_stock_mutation.html", {"form": form})


@roleRequired(Role.ADMIN)
def edit_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = FormProduct(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Produk '{product.name}' berhasil diperbarui.")
        else:
            _flash_form_errors(request, form)
    return redirect("product:manage_product")


@roleRequired(Role.ADMIN)
def delete_product(request, pk):
    if request.method == "POST":
        product = get_object_or_404(Product, pk=pk)
        name = product.name
        try:
            product.delete()
            messages.success(request, f"Produk '{name}' berhasil dihapus.")
        except ProtectedError:
            messages.error(
                request,
                f"Produk '{name}' tidak bisa dihapus karena sudah punya riwayat mutasi stok. "
                "Nonaktifkan produk ini saja lewat tombol Update.",
            )
    return redirect("product:manage_product")
