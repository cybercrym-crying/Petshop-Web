from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("customer/dashboard", views.customer, name="customer_dashboard"),
    path("cashier/dashboard", views.cashier, name="cashier_dashboard"),
    path("warehouse/dashboard", views.warehouse, name="warehouse_dashboard"),
    path("service/dashboard", views.service, name="service_dashboard"),
    path("register", views.register_form, name="register_form"),
    path("register/success", views.register_success_view, name="register_success"),
    path("login", views.login_form, name="login_form"),
    path("logout", views.logout_form, name="logout"),
]
