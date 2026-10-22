import re

from django.db.models import Count, ProtectedError, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from .models import STAFF_ROLES, Customer, Role
from .form import CustomerForm, LoginForm, EmployeeForm, RegisterForm
from .decorators import roleRequired
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from transaction.models import Order, OrderStatus
from django.db.models import Sum
from service.models import BookingStatus

User = get_user_model()


def _whatsapp_url(phone):
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return f"https://wa.me/{digits}"


def _next_url(request, default):
    """Tujuan redirect dari field `next`, hanya jika aman (host sendiri)."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


def loginForm(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(_next_url(request, None) or user.dashboard_url_name)
        else:
            errorMessage = "Nama pengguna atau kata sandi salah"
            form = LoginForm()
            return render(
                request, "account/login.html", {"error": errorMessage, "form": form}
            )
    else:
        form = LoginForm()
        return render(request, "account/login.html", {"form": form})


def register(request):
    """Daftar akun pelanggan (role CUSTOMER) dari situs toko."""
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name)
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Akun berhasil dibuat. Selamat datang!")
        return redirect(_next_url(request, None) or "service:catalog")
    return render(
        request,
        "account/register.html",
        {"form": form, "next": request.POST.get("next") or request.GET.get("next", "")},
    )


def logoutForm(request):
    if request.method == "POST":
        logout(request)
        return redirect("customer:shop")
    return redirect("customer:shop")


@roleRequired(Role.ADMIN)
def staff_admin_dashboard(request):
    # Menu admin sekarang ada di sidebar; halaman awal admin = Manage User.
    return redirect("manage_account")


@roleRequired(Role.ADMIN)
def manage_account(request):
    employees = (
        User.objects.filter(role__in=STAFF_ROLES)
        .annotate(
            created_count=Count("order", distinct=True),
            delivered_count=Count(
                "orders_as_courier",
                filter=Q(orders_as_courier__order_status=OrderStatus.DELIVERED),
                distinct=True,
            ),
            groomed_count=Count(
                "grooming_jobs",
                filter=Q(grooming_jobs__status=BookingStatus.DONE),
                distinct=True,
            ),
        )
        .order_by("first_name", "username")
    )
    context = {
        "active_tab": request.GET.get("tab", "employee"),
        "employee": list(employees),
        "customers": Customer.objects.order_by("first_name", "last_name"),
        "staff_roles": [(code, Role(code).label) for code in STAFF_ROLES],
    }
    return render(request, "account/manage_account.html", context)


@roleRequired(Role.ADMIN)
def employee_profile(request, pk):
    emp = get_object_or_404(User, pk=pk, role__in=STAFF_ROLES)
    behavior = emp.role_behavior
    is_courier = behavior.code == Role.COURIER
    recent_orders, recent_bookings = [], []
    if behavior.work_kind == "bookings":
        jobs = behavior.handled_bookings(emp)
        agg = jobs.aggregate(
            total=Count("pk"),
            process=Count("pk", filter=Q(status=BookingStatus.PROCESS)),
            done=Count("pk", filter=Q(status=BookingStatus.DONE)),
        )
        recent_bookings = list(
            jobs.select_related("customer", "service").order_by("-schedule")[:5]
        )
    else:
        handled = behavior.handled_orders(emp)
        agg = handled.aggregate(
            total=Count("pk"),
            confirmed=Count("pk", filter=Q(order_status=OrderStatus.CONFIRMED)),
            on_delivery=Count("pk", filter=Q(order_status=OrderStatus.ON_DELIVERY)),
            delivered=Count("pk", filter=Q(order_status=OrderStatus.DELIVERED)),
        )
        recent_orders = list(handled.select_related("customer").order_by("-date")[:5])
    return render(
        request,
        "account/employee_profile.html",
        {
            "emp": emp,
            "is_courier": is_courier,
            "is_self": emp == request.user,
            "stats": behavior.statistic_cards(agg),
            "work_kind": behavior.work_kind,
            "recent_orders": recent_orders,
            "recent_bookings": recent_bookings,
            "staff_roles": [(code, Role(code).label) for code in STAFF_ROLES],
            "wa_url": _whatsapp_url(emp.phone_number),
        },
    )


@roleRequired(Role.ADMIN)
def customer_profile(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    recent_orders = Order.objects.filter(customer=customer).order_by("-date")[:10]
    recent_bookings = customer.service_bookings.select_related(
        "service", "groomer"
    ).order_by("-schedule")[:10]
    total_orders = Order.objects.filter(customer=customer).count()
    total_spent = (
        Order.objects.filter(customer=customer).aggregate(total=Sum("total_payment"))[
            "total"
        ]
        or 0
    )
    stats = [
        {"value": total_orders, "label": "Total Pesanan"},
        {"value": f"Rp {total_spent:,.0f}".replace(",", "."), "label": "Total Belanja"},
    ]

    context = {
        "customer": customer,
        "recent_orders": recent_orders,
        "recent_bookings": recent_bookings,
        "stats": stats,
    }

    return render(request, "account/customer_profile.html", context)


@roleRequired(Role.ADMIN)
def add_employee(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Karyawan berhasil ditambahkan.")
        else:
            _flash_form_errors(request, form)
    return redirect("manage_account")


@roleRequired(Role.ADMIN)
def delete_employee(request, pk):
    back = _next_url(request, reverse("manage_account"))
    if request.method == "POST":
        employee = get_object_or_404(User, pk=pk, role__in=STAFF_ROLES)
        if employee == request.user:
            messages.error(request, "Kamu tidak bisa menghapus akunmu sendiri.")
            return redirect(back)
        try:
            employee.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Karyawan '{employee.username}' tidak bisa dihapus karena sudah punya riwayat order/layanan.",
            )
            return redirect(back)
        messages.success(request, "Karyawan berhasil dihapus.")
    return redirect("manage_account")


def _customer_tab():
    return redirect(f"{reverse('manage_account')}?tab=customer")


def _flash_form_errors(request, form):
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else field
        for error in errors:
            messages.error(request, f"{label}: {error}")


@roleRequired(Role.ADMIN)
def add_customer(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Pelanggan berhasil ditambahkan.")
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def edit_employee(request, pk):
    employee = get_object_or_404(User, pk=pk, role__in=STAFF_ROLES)
    originalRole = employee.role
    back = _next_url(request, reverse("manage_account"))
    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            if employee == request.user and form.cleaned_data["role"] != originalRole:
                messages.error(
                    request, "Kamu tidak bisa mengubah peran akunmu sendiri."
                )
                return redirect(back)
            form.save()
            if employee == request.user and form.cleaned_data.get("password"):
                # set_password mengubah hash sesi; tanpa ini admin ter-logout sendiri.
                update_session_auth_hash(request, employee)
            messages.success(request, "Data karyawan berhasil diperbarui.")
        else:
            _flash_form_errors(request, form)
    return redirect(back)


@roleRequired(Role.ADMIN)
def edit_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Data pelanggan berhasil diperbarui.")
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def delete_customer(request, pk):
    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=pk)
        try:
            customer.delete()
            messages.success(request, "Pelanggan berhasil dihapus.")
        except ProtectedError:
            messages.error(
                request,
                f"Pelanggan '{customer.name}' tidak bisa dihapus karena sudah punya riwayat order/booking.",
            )
    return _customer_tab()
