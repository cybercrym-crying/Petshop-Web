from django.urls import path
from . import views

urlpatterns = [
    # --- Publik, tidak perlu login ---
    path("", views.home, name="home"),
    path("register", views.registerForm, name="register_form"),
    path("register/success", views.registerSuccessView, name="register_success"),
    path("login", views.loginForm, name="login_form"),
    path("logout", views.logoutForm, name="logout"),

    # --- Customer: perlu login, tetap di main site (bukan /staff/) ---
    path("customer/dashboard", views.customerDashboard, name="customer_dashboard"),

    # --- Staff: perlu login + role check, sengaja di prefix /staff/
    # (bukan /admin/) supaya tidak bentrok dengan Django admin bawaan yang
    # tetap ada di /admin/ untuk superuser). ---
    path("staff/owner/dashboard", views.staffOwnerDashboard, name="staff_owner_dashboard"),
    path("staff/cashier/dashboard", views.staffCashierDashboard, name="staff_cashier_dashboard"),
    path("staff/warehouse/dashboard", views.staffWarehouseDashboard, name="staff_warehouse_dashboard"),
    path("staff/service/dashboard", views.staffServiceDashboard, name="staff_service_dashboard"),
]