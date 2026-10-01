from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import ProtectedError
from .models import Category, Product, StockMutation, MutationType
from .form import FormProduct, StockMutationForm, SellingPriceForm
from account.models import Role
from account.decorators import roleRequired


@roleRequired(Role.ADMIN)
def manage_product(request):
    products = Product.objects.select_related("category").order_by("name")
    category = request.GET.get("category")
    q = request.GET.get("q")
    if category:
        products = products.filter(category_id=category)
    if q:
        products = products.filter(name__icontains=q)
    return render(
        request,
        "product/manage_product.html",
        {
            "products": products,
            "categories": Category.objects.all(),
        },
    )


@roleRequired(Role.ADMIN)
def add_product(request):
    if request.method == "POST":
        form = FormProduct(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            if product.stock > 0:
                StockMutation.objects.create(
                    product=product,
                    mutationType=MutationType.IN,
                    quantity=product.stock,
                    note="Stok awal saat produk dibuat",
                    createdBy=request.user,
                )
            messages.success(request, f"Produk '{product.name}' berhasil ditambahkan")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    return redirect("product:manage_product")


@roleRequired(Role.ADMIN)
def product_list(request):
    productQueryset = Product.objects.select_related("category").all().order_by("name")
    return render(
        request, "product/product_list.html", {"productList": productQueryset}
    )


def productCatalog(request):
    productQueryset = (
        Product.objects.filter(is_active=True, selling_price__isnull=False)
        .select_related("category")
        .order_by("name")
    )
    return render(request, "product/catalog.html", {"productList": productQueryset})


@roleRequired(Role.ADMIN)
def set_selling_price(request, productId):
    product = get_object_or_404(Product, id=productId)
    if request.method == "POST":
        form = SellingPriceForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Selling price '{product.name}' updating success"
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
            with transaction.atomic():
                mutation = form.save(commit=False)
                mutation.createdBy = request.user
                mutation.save()

                product = mutation.product
                if mutation.mutationType == MutationType.IN:
                    product.stock += mutation.quantity
                else:
                    product.stock -= mutation.quantity
                product.save(update_fields=["stock", "updated_at"])

            messages.success(request, "Creat mutation stock success")
            return redirect("product:product_list")
    else:
        form = StockMutationForm()
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
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
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
