from django.urls import path
from . import views, views_pos

# urls.py
app_name = "transaction"
urlpatterns = [
    path(
        "staff/admin/make_transaction/", views_pos.make_transaction, name="make_transaction"
    ),
    path("staff/admin/kasir/scan/", views_pos.scan, name="pos_scan"),
    path("staff/admin/kasir/booking/", views_pos.add_booking, name="pos_add_booking"),
    path("staff/admin/kasir/booking/<int:pk>/hapus/", views_pos.remove_booking, name="pos_remove_booking"),
    path("staff/admin/kasir/pelanggan/", views_pos.quick_customer, name="quick_customer"),
    path("staff/admin/kasir/parkir/", views_pos.hold_sale, name="pos_hold"),
    path("staff/admin/kasir/parkir/<int:pk>/", views_pos.resume_sale, name="pos_resume"),
    path("staff/kasir/", views_pos.cashier_home, name="cashier_home"),
    path("staff/kasir/shift/", views_pos.shift, name="shift"),
    path("staff/admin/transaction/<int:pk>/struk/", views_pos.receipt, name="receipt"),
    path("staff/admin/transaction/<int:pk>/batal/", views_pos.void_transaction, name="void"),
    path("staff/admin/transaction/<int:pk>/retur/", views_pos.return_create, name="return_create"),
    path("staff/admin/retur/", views_pos.returns, name="returns"),
    path("staff/admin/retur/<int:pk>/putuskan/", views_pos.return_decide, name="return_decide"),
    path("staff/admin/laporan-kasir/", views_pos.cashier_report_view, name="cashier_report"),
    path("staff/admin/produk/kode-barang/", views_pos.product_codes, name="product_codes"),
    path("staff/admin/produk/<int:pk>/kode.svg", views_pos.product_code_qr, name="product_code_qr"),
    path("struk/<str:token>/", views_pos.receipt_public, name="receipt_public"),
    path("struk/<str:token>/qr.svg", views_pos.receipt_qr, name="receipt_qr"),
    path(
        "staff/admin/manage_transaction/",
        views.manage_transaction,
        name="manage_transaction",
    ),
    path(
        "staff/admin/transaction/<int:pk>/status/",
        views.update_status,
        name="update_status",
    ),
    path(
        "staff/admin/transaction/<int:pk>/pembayaran/",
        views.payment_check,
        name="payment_check",
    ),
    path("staff/admin/packing/", views.packing_queue, name="packing_queue"),
    path("staff/admin/setoran-cod/", views.remittances, name="remittances"),
    path("staff/admin/transaction/<int:pk>/label/", views.print_label, name="print_label"),
    path("staff/admin/transaction/<int:pk>/label/qr.svg", views.label_qr, name="label_qr"),
    path("staff/admin/cart/add/<int:pk>/", views.add_to_cart, name="add_to_cart"),
    path(
        "staff/admin/cart/update/<int:pk>/",
        views.update_cart_quantity,
        name="update_cart_quantity",
    ),
    path(
        "staff/admin/cart/remove/<int:pk>/",
        views.remove_from_cart,
        name="remove_from_cart",
    ),
    path(
        "staff/admin/cart/cancel/", views.cancel_transaction, name="cancel_transaction"
    ),
    path(
        "staff/admin/cart/submit/", views_pos.submit_transaction, name="submit_transaction"
    ),
]
