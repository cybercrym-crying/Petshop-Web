from django.urls import path

from . import views

app_name = "service"

urlpatterns = [
    # Situs pelanggan
    path("layanan/", views.catalog, name="catalog"),
    path("layanan/booking-saya/", views.my_bookings, name="my_bookings"),
    # Admin & kasir
    path("staff/layanan/booking/", views.manage_bookings, name="manage_bookings"),
    path("staff/layanan/booking/tambah/", views.create_booking, name="create_booking"),
    path(
        "staff/layanan/booking/<int:pk>/groomer/",
        views.assign_groomer,
        name="assign_groomer",
    ),
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
]
