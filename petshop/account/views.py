import re

from django.db.models import Count, ProtectedError, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import Customer, Role
from .form import CustomerForm, LoginForm, EmployeeForm
from .decorators import roleRequired
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from product.models import Product
from transaction.models import Order, OrderStatus

User = get_user_model()

AVATAR_TONES = 6


def _decorate_employee(emp):
    """Tambah atribut tampilan: nama, inisial, dan warna avatar (stabil per user)."""
    first = (emp.first_name or "").strip()
    last = (emp.last_name or "").strip()
    emp.display_name = f"{first} {last}".strip() or emp.username
    emp.initials = ((first[:1] + last[:1]) or emp.username[:2]).upper()
    emp.tone = emp.pk % AVATAR_TONES
    return emp


def _whatsapp_url(phone):
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return f"https://wa.me/{digits}"


def _next_url(request, default):
    """Tujuan redirect dari field `next`, hanya jika aman (host sendiri)."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


def home(request):
    return render(request, "index.html")


def customerForm(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data.get("name")
            phoneNumber = form.cleaned_data.get("phone_number")
            address = form.cleaned_data.get("address")

            Customer.objects.create(
                name=name, phone_number=phoneNumber, address=address
            )

            return redirect("register_success")
    else:
        form = CustomerForm()
    return render(request, "account/register.html", {"form": form})


def loginForm(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(user.dashboard_url_name)
        else:
            errorMessage = "Invalid Credential"
            form = LoginForm()
            return render(
                request, "account/login.html", {"error": errorMessage, "form": form}
            )
    else:
        form = LoginForm()
        return render(request, "account/login.html", {"form": form})


def logoutForm(request):
    if request.method == "POST":
        logout(request)
        return redirect("customer:katalog")
    return redirect("customer:katalog")


def customerDashboard(request):
    return render(
        request, "customer/dashboard.html", {"username": request.user.username}
    )


@roleRequired(Role.ADMIN)
def staff_admin_dashboard(request):
    return render(
        request, "staff/admin/dashboard.html", {"username": request.user.username}
    )


@roleRequired(Role.ADMIN)
def manage_account(request):
    employees = (
        User.objects.filter(role__in=[Role.ADMIN, Role.COURIER])
        .annotate(
            created_count=Count("order", distinct=True),
            delivered_count=Count(
                "orders_as_courier",
                filter=Q(orders_as_courier__order_status=OrderStatus.DELIVERED),
                distinct=True,
            ),
        )
        .order_by("first_name", "username")
    )
    context = {
        "active_tab": request.GET.get("tab", "employee"),
        "employee": [_decorate_employee(e) for e in employees],
        "customers": Customer.objects.all(),
    }
    return render(request, "staff/admin/manage_account.html", context)


@roleRequired(Role.ADMIN)
def employee_profile(request, pk):
    emp = _decorate_employee(
        get_object_or_404(User, pk=pk, role__in=[Role.ADMIN, Role.COURIER])
    )
    is_courier = emp.role == Role.COURIER
    handled = (
        Order.objects.filter(courier=emp) if is_courier else Order.objects.filter(admin=emp)
    )
    agg = handled.aggregate(
        total=Count("pk"),
        confirmed=Count("pk", filter=Q(order_status=OrderStatus.CONFIRMED)),
        on_delivery=Count("pk", filter=Q(order_status=OrderStatus.ON_DELIVERY)),
        delivered=Count("pk", filter=Q(order_status=OrderStatus.DELIVERED)),
    )
    if is_courier:
        stats = [
            {"value": agg["total"], "label": "Assigned", "tone": ""},
            {"value": agg["on_delivery"], "label": "On delivery", "tone": "blue"},
            {"value": agg["delivered"], "label": "Delivered", "tone": "green"},
        ]
    else:
        stats = [
            {"value": agg["total"], "label": "Orders created", "tone": ""},
            {"value": agg["confirmed"] + agg["on_delivery"], "label": "Still open", "tone": "blue"},
            {"value": agg["delivered"], "label": "Delivered", "tone": "green"},
        ]
    return render(
        request,
        "staff/admin/employee_profile.html",
        {
            "emp": emp,
            "is_courier": is_courier,
            "is_self": emp == request.user,
            "stats": stats,
            "recent_orders": list(handled.select_related("customer").order_by("-date")[:5]),
            "wa_url": _whatsapp_url(emp.phone_number),
        },
    )


@roleRequired(Role.ADMIN)
def add_employee(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Add employee success")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    return redirect("manage_account")


@roleRequired(Role.ADMIN)
def delete_employee(request, pk):
    back = _next_url(request, reverse("manage_account"))
    if request.method == "POST":
        employee = get_object_or_404(User, pk=pk)
        if employee == request.user:
            messages.error(request, "You cannot delete your account.")
            return redirect(back)
        try:
            employee.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Employee '{employee.username}' tidak bisa dihapus karena sudah punya riwayat order.",
            )
            return redirect(back)
        messages.success(request, "Delete employee success")
    return redirect("manage_account")


def _customer_tab():
    return redirect(f"{reverse('manage_account')}?tab=customer")


def _flash_form_errors(request, form):
    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, f"{field}: {error}")


@roleRequired(Role.ADMIN)
def add_customer(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Add customer success.")
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def edit_employee(request, pk):
    employee = get_object_or_404(User, pk=pk)
    originalRole = employee.role
    back = _next_url(request, reverse("manage_account"))
    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            if employee == request.user and form.cleaned_data["role"] != originalRole:
                messages.error(request, "You cannot change your account role.")
                return redirect(back)
            form.save()
            messages.success(request, "Edit employee success")
        else:
            messages.error(request, f"Failed to edit employee {form.errors}.")
    return redirect(back)


@roleRequired(Role.ADMIN)
def edit_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Edit customer success.")
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def delete_customer(request, pk):
    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=pk)
        try:
            customer.delete()
            messages.success(request, "Delete customer success")
        except ProtectedError:
            messages.error(
                request,
                f"Customer '{customer.name}' tidak bisa dihapus karena sudah punya riwayat order.",
            )
    return _customer_tab()
