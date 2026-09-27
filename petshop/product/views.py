from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from .models import Product, StockMutation, MutationType
from .form import FormProduct, StockMutationForm, SellingPriceForm
from account.models import Role
from account.decorators import roleRequired


@roleRequired(Role.STAF_GUDANG)
def addNewProduct(request):
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
            messages.success(request, f"Produk '{product.name}' berhasil ditambahkan.")
            return redirect("product_list")
    else:
        form = FormProduct()
    return render(request, "product/add_product.html", {"form": form})


@roleRequired(Role.OWNER, Role.KASIR, Role.STAF_GUDANG)
def productList(request):
    productQueryset = Product.objects.select_related("category").all().order_by("name")
    return render(request, "product/product_list.html", {"productList": productQueryset})


def productCatalog(request):
    productQueryset = Product.objects.filter(
        isActive=True, sellingPrice__isnull=False
    ).select_related("category").order_by("name")
    return render(request, "product/catalog.html", {"productList": productQueryset})


@roleRequired(Role.OWNER)
def setSellingPrice(request, productId):
    product = get_object_or_404(Product, id=productId)
    if request.method == "POST":
        form = SellingPriceForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Harga jual '{product.name}' berhasil diupdate.")
            return redirect("product_list")
    else:
        form = SellingPriceForm(instance=product)
    return render(request, "product/set_price.html", {"form": form, "product": product})


@roleRequired(Role.STAF_GUDANG)
def addStockMutation(request):
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
                product.save(update_fields=["stock", "updatedAt"])

            messages.success(request, "Mutasi stok berhasil dicatat.")
            return redirect("product_list")
    else:
        form = StockMutationForm()
    return render(request, "product/add_stock_mutation.html", {"form": form})