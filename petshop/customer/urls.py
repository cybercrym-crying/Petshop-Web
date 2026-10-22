from django.urls import path

from . import views

app_name = "customer"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.shop, name="shop"),
    path("produk/", views.products, name="products"),
    path("produk/<int:pk>/", views.product_detail, name="product_detail"),
    path("about/", views.about, name="about"),
    path("favorit/", views.wishlist, name="wishlist"),
    path("favorit/produk/", views.wishlist_items, name="wishlist_items"),
    path("lacak/", views.track_order, name="track"),
    path("lacak/<str:resi>/", views.track_order, name="track_detail"),
    path("lacak/<str:resi>/lokasi/", views.track_location, name="track_location"),
    path("cart", views.cart_page, name="cart"),
    path("checkout", views.checkout_page, name="checkout"),
    path("checkout/pesan/", views.place_order, name="place_order"),
    path("pesanan-saya/", views.my_orders, name="my_orders"),
    path("pesanan-saya/<int:pk>/batal/", views.cancel_my_order, name="cancel_my_order"),
]
