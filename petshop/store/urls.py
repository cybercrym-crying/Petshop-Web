from django.urls import path

from . import views

app_name = "store"

urlpatterns = [
    path("staff/admin/pengaturan-toko/", views.store_settings, name="settings"),
    path("notifikasi/", views.notifications, name="notifications"),
    path("notifikasi/<int:pk>/buka/", views.open_notification, name="open_notification"),
    path("notifikasi/baca-semua/", views.read_all_notifications, name="read_all"),
    path("komplain/", views.complaints, name="complaints"),
    path("staff/admin/komplain/", views.staff_complaints, name="staff_complaints"),
    path("staff/admin/komplain/<int:pk>/", views.staff_complaint, name="staff_complaint"),
    path("staff/admin/ulasan/", views.reviews, name="reviews"),
]
