from django.urls import path
from . import views

# urls.py
app_name = "transaction"
urlpatterns = [
    path(
        "staff/admin/make_transaction/", views.make_transaction, name="make_transaction"
    ),
    path("staff/admin/cart/add/<int:pk>/", views.add_to_cart, name="add_to_cart"),
    path(
        "staff/admin/cart/remove/<int:pk>/",
        views.remove_from_cart,
        name="remove_from_cart",
    ),
    path(
        "staff/admin/cart/cancel/", views.cancel_transaction, name="cancel_transaction"
    ),
    path(
        "staff/admin/cart/submit/", views.submit_transaction, name="submit_transaction"
    ),
]
