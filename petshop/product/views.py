from django.shortcuts import render
from .models import Product


def add_new_product(request):
    if request.method == "POST":
        category = request.POST.get("category")
        name = request.POST.get("name")
        selling_price = request.POST.get("selling_price")
        purchase_price = request.POST.get("purchase_price")
        stock = request.POST.get("stock")
        is_active = request.POST.get("stock")
        image = request.POST.get("image")
        product = Product.objects.create(
            category=category,
            name=name,
            selling_price=selling_price,
            purchase_price=purchase_price,
            stock=stock,
            is_active=is_active,
            image=image,
        )


# Create your views here.
