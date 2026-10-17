from django.urls import path

from . import views

app_name = "courier"

urlpatterns = [
    path("staff/courier/dashboard", views.dashboard, name="dashboard"),
    path("staff/courier/history", views.history, name="history"),
    path("staff/courier/order/<int:pk>/", views.order_detail, name="order_detail"),
    path(
        "staff/courier/order/<int:pk>/status/",
        views.update_status,
        name="update_status",
    ),
]
