from django.urls import path
from . import views

app_name = "customer"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.katalog_publik, name="katalog"),
    path("about/", views.about, name="about"),
    path("cart", views.cart_page, name="cart"),
    path("checkout", views.checkout_page, name="checkout"),
]

