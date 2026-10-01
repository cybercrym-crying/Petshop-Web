from django.urls import path
from . import views

urlpatterns = [
    # --- Publik, tidak perlu login ---
    path("", views.home, name="home"),
    path("login", views.loginForm, name="login_form"),
    path("logout", views.logoutForm, name="logout"),
    # --- Customer: perlu login, tetap di main site (bukan /staff/) ---
    path("customer/dashboard", views.customerDashboard, name="customer_dashboard"),
    # --- Staff: perlu login + role check, sengaja di prefix /staff/
    # (bukan /admin/) supaya tidak bentrok dengan Django admin bawaan yang
    # tetap ada di /admin/ untuk superuser). ---
    path(
        "staff/admin/dashboard",
        views.staff_admin_dashboard,
        name="staff_admin_dashboard",
    ),
    path(
        "staff/admin/manage_account",
        views.manage_account,
        name="manage_account",
    ),
    path("staff/admin/employee/add/", views.add_employee, name="add_employee"),
    path(
        "staff/admin/employee/<int:pk>/edit/", views.edit_employee, name="edit_employee"
    ),
    path(
        "staff/admin/employee/<int:pk>/delete/",
        views.delete_employee,
        name="delete_employee",
    ),
    path("staff/admin/customer/add/", views.add_customer, name="add_customer"),
    path(
        "staff/admin/customer/<int:pk>/edit/", views.edit_customer, name="edit_customer"
    ),
    path(
        "staff/admin/customer/<int:pk>/delete/",
        views.delete_customer,
        name="delete_customer",
    ),
]
