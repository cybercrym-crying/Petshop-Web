from django.urls import path
from . import views  # Pastikan hanya meng-import views, BUKAN include

app_name = "customer"

urlpatterns = [
    path("", views.katalog_publik, name="katalog"),
    path("pesan", views.form_pemesanan_publik, name="pesan"),
    path("cart", views.cart_page, name="cart"),
    path("checkout", views.checkout_page, name="checkout"),
]