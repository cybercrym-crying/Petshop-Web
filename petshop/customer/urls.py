from django.urls import path

from . import views

app_name = "customer"

urlpatterns = [
    path("", views.home, name="home"),
    path("home-shop/", views.home_shop, name="home_shop"),
    path("shop/", views.shop, name="shop"),
    path("product/<int:pk>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_page, name="cart"),
    path("checkout/", views.checkout_page, name="checkout"),
    path("order/", views.place_order, name="place_order"),
]
