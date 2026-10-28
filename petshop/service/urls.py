from django.urls import path

from . import views

app_name = "service"

urlpatterns = [
    # Situs pelanggan
    path("layanan/", views.catalog, name="catalog"),
    path("layanan/booking-saya/", views.my_bookings, name="my_bookings"),
    path(
        "layanan/booking-saya/<int:pk>/batal/",
        views.cancel_my_booking,
        name="cancel_my_booking",
    ),
    path("layanan/booking-saya/<int:pk>/qr.svg", views.booking_qr, name="booking_qr"),
    path("layanan/booking-saya/<int:pk>/bayar/", views.booking_payment, name="booking_payment"),
    path("layanan/booking-saya/<int:pk>/ulas/", views.rate_booking, name="rate_booking"),
    path("layanan/booking-saya/<int:pk>/lokasi/", views.booking_location, name="booking_location"),
    path("layanan/booking/<int:pk>/", views.booking_share, name="booking_share"),
    path("layanan/booking/<int:pk>/qr.svg", views.booking_share_qr, name="booking_share_qr"),
    path("layanan/hewan-saya/", views.my_pets, name="my_pets"),
    path("layanan/hewan-saya/tambah/", views.edit_pet, name="add_pet"),
    path("layanan/hewan-saya/<int:pk>/", views.edit_pet, name="edit_pet"),
    # Admin & kasir
    path("staff/layanan/booking/", views.manage_bookings, name="manage_bookings"),
    path("staff/layanan/booking/tambah/", views.create_booking, name="create_booking"),
    path(
        "staff/layanan/booking/<int:pk>/groomer/",
        views.assign_groomer,
        name="assign_groomer",
    ),
    path(
        "staff/layanan/booking/<int:pk>/batal/",
        views.cancel_booking,
        name="cancel_booking",
    ),
    path("staff/layanan/booking/<int:pk>/aksi/", views.booking_action, name="booking_action"),
    path("staff/layanan/booking/<int:pk>/pembayaran/", views.booking_payment_check, name="booking_payment_check"),
    path("staff/layanan/check-in/", views.check_in, name="check_in"),
    path("staff/admin/layanan/<int:pk>/tahapan/", views.service_steps, name="service_steps"),
    path("staff/admin/layanan/", views.manage_services, name="manage_services"),
    path("staff/admin/layanan/tambah/", views.save_service, name="add_service"),
    path("staff/admin/layanan/<int:pk>/edit/", views.save_service, name="edit_service"),
    # Groomer
    path("staff/groomer/dashboard", views.groomer_dashboard, name="groomer_dashboard"),
    path(
        "staff/groomer/booking/<int:pk>/",
        views.groomer_booking_detail,
        name="groomer_booking_detail",
    ),
    path(
        "staff/groomer/booking/<int:pk>/status/",
        views.groomer_update_status,
        name="groomer_update_status",
    ),
    # Kurir antar-jemput hewan
    path("staff/courier/hewan/", views.courier_pets, name="courier_pets"),
    path("staff/courier/hewan/<int:pk>/", views.courier_pet_trip, name="courier_pet_trip"),
    path("staff/courier/hewan/<int:pk>/cek/", views.courier_pet_check, name="courier_pet_check"),
]
