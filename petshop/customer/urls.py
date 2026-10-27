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
    path("lacak/<str:resi>/qr.svg", views.tracking_qr, name="tracking_qr"),
    path("lacak/<str:resi>/serah-terima.svg", views.track_handover_qr, name="track_handover_qr"),
    path("cart", views.cart_page, name="cart"),
    path("keranjang/cek/", views.cart_check, name="cart_check"),
    path("checkout", views.checkout_page, name="checkout"),
    path("checkout/pesan/", views.place_order, name="place_order"),
    path("checkout/ongkir/", views.shipping_quote, name="shipping_quote"),
    path("dasbor/", views.dashboard, name="dashboard"),
    path("akun/", views.account, name="account"),
    path("pesanan-saya/", views.my_orders, name="my_orders"),
    path("pesanan-saya/<int:pk>/batal/", views.cancel_my_order, name="cancel_my_order"),
    path("pesanan-saya/<int:pk>/ulas/", views.rate_order, name="rate_order"),
    path("pesanan-saya/<int:pk>/bukti-transfer/", views.payment_proof, name="payment_proof"),
    path("pesanan-saya/<int:pk>/qr-serah-terima.svg", views.handover_qr, name="handover_qr"),
]
