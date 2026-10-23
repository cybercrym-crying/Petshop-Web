from django.urls import path

from . import views

app_name = "courier"

urlpatterns = [
    path("staff/courier/dashboard", views.dashboard, name="dashboard"),
    path("staff/courier/rute.json", views.route_data, name="route_data"),
    path("staff/courier/rute/hitung-ulang/", views.reroute, name="reroute"),
    path("staff/courier/paket", views.packages, name="packages"),
    path("staff/courier/ambil/", views.pickup, name="pickup"),
    path("staff/courier/setoran/", views.cash, name="cash"),
    path("staff/courier/history", views.history, name="history"),
    path("staff/courier/lokasi/", views.share_location, name="share_location"),
    path("staff/courier/order/<int:pk>/", views.order_detail, name="order_detail"),
    path("staff/courier/order/<int:pk>/serah/", views.handover, name="handover"),
    path("staff/courier/order/<int:pk>/serah/cek/", views.check_handover, name="check_handover"),
    path("staff/courier/order/<int:pk>/kendala/", views.report_problem, name="problem"),
]
