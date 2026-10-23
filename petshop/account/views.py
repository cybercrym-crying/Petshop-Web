import csv
import re

from django.utils.translation import gettext as _
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from .models import STAFF_ROLES, Approval, Customer, Role
from .form import CustomerForm, LoginForm, EmployeeForm, RegisterForm, StaffRegisterForm
from .decorators import roleRequired
from . import dashboard
from django.contrib import messages
from django.core.cache import cache
from django.utils.http import url_has_allowed_host_and_scheme
from transaction.models import Order, OrderStatus, PaymentStatus
from django.db.models import Sum
from service.models import WORK_DONE_STATUSES, BookingStatus

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


LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60


def _login_throttle_key(request, username):
    ip = request.META.get("REMOTE_ADDR", "")
    return f"login-fail:{(username or '').strip().lower()}:{ip}"


def loginForm(request):
    from store.models import StoreSettings

    context = {"form": LoginForm(), "wa_link": StoreSettings.current().whatsapp_link}
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        context["username"] = username
        key = _login_throttle_key(request, username)
        failures = cache.get(key, 0)
        if failures >= LOGIN_MAX_FAILURES:
            context["error"] = (
                "Terlalu banyak percobaan masuk yang gagal. "
                "Coba lagi dalam 15 menit atau hubungi admin."
            )
            return render(request, "account/login.html", context, status=429)
        user = authenticate(request, username=username, password=password)
        if user is not None:
            cache.delete(key)
            login(request, user)
            return redirect(_next_url(request, None) or user.dashboard_url_name)
        cache.set(key, failures + 1, LOGIN_LOCK_SECONDS)
        context["error"] = _inactive_reason(username, password) or "Nama pengguna atau kata sandi salah"
    return render(request, "account/login.html", context)


def _inactive_reason(username, password):
    """Pesan khusus untuk staf yang kata sandinya benar tapi akunnya belum aktif."""
    user = User.objects.filter(username__iexact=(username or "").strip()).first()
    if user is None or user.is_active or not user.check_password(password):
        return ""
    if user.approval == Approval.PENDING:
        return "Akun Anda masih menunggu persetujuan admin. Anda akan bisa masuk setelah disetujui."
    if user.approval == Approval.REJECTED:
        return "Pendaftaran Anda tidak disetujui. Hubungi admin toko untuk informasi lebih lanjut."
    return "Akun ini dinonaktifkan. Hubungi admin toko."


def register_staff(request):
    """Pendaftaran kasir/kurir/groomer. Akun aktif setelah disetujui admin."""
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name)
    form = StaffRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        staff = form.save()
        from store.models import Notification

        Notification.to_staff(
            (Role.SUPERADMIN, Role.ADMIN),
            "Pendaftaran staf baru",
            f"{staff.name} mendaftar sebagai {staff.get_role_display()}.",
            reverse("manage_account") + "?tab=approval",
        )
        return render(request, "account/register_staff_done.html", {"staff": staff})
    return render(request, "account/register_staff.html", {"form": form})


def register(request):
    """Daftar akun pelanggan (role CUSTOMER) dari situs toko."""
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name)
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, _("Akun berhasil dibuat. Selamat datang!"))
        return redirect(_next_url(request, None) or "customer:dashboard")
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
    """Ringkasan toko untuk admin: penjualan, pekerjaan yang menunggu, stok, booking."""
    days = dashboard.parse_range(request.GET.get("range"))
    period = dashboard.Period.last_days(days)
    # Hari ini: grafik tetap 14 hari agar ada gambaran tren.
    trend = dashboard.sales_trend(period if days > 1 else dashboard.Period.last_days(14))
    top = dashboard.top_products(period)
    best = max(trend, key=lambda p: p["total"], default=None)
    for row in top:
        row["pct"] = round(row["qty"] * 100 / top[0]["qty"]) if top and top[0]["qty"] else 0
    bookings = dashboard.bookings_today()
    for b in bookings:
        b.tone = dashboard.BOOKING_TONES.get(b.status, "mute")
    recent = dashboard.recent_orders()
    for o in recent:
        o.tone = dashboard.ORDER_TONES.get(o.order_status, "mute")
    return render(
        request,
        "account/admin_dashboard.html",
        {
            "days": days,
            "range_choices": dashboard.RANGE_CHOICES,
            "period": period,
            "summary": dashboard.summary(period),
            "compare": dashboard.comparison(period),
            "tasks": dashboard.staff_tasks(request.user),
            "cashier": dashboard.cashier_now(),
            "couriers": dashboard.couriers_now(),
            "trend": trend,
            "trend_days": len(trend),
            "trend_peak": best["total"] if best else 0,
            "trend_best": best if best and best["total"] else None,
            "top_products": top,
            "bookings": bookings,
            "low_stock": dashboard.low_stock_products(),
            "recent_orders": recent,
        },
    )


@roleRequired(Role.ADMIN)
def sales_report_csv(request):
    """Unduh daftar order pada rentang dasbor (CSV, bisa dibuka di Excel)."""
    days = dashboard.parse_range(request.GET.get("range"))
    period = dashboard.Period.last_days(days)
    orders = (
        dashboard.orders_in(period)
        .select_related("customer", "admin", "courier")
        .order_by("date", "pk")
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"laporan-penjualan-{timezone.localdate():%Y%m%d}-{days}hari.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # BOM supaya Excel membaca UTF-8
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "No. Order",
            "Resi",
            "Tanggal",
            "Saluran",
            "Pelanggan",
            "Status Order",
            "Metode Bayar",
            "Status Bayar",
            "Total (Rp)",
            "Dihitung sebagai penjualan",
        ]
    )
    for order in orders:
        counted = (
            order.payment_status == PaymentStatus.PAID
            and order.order_status != OrderStatus.CANCELLED
        )
        writer.writerow(
            [
                order.pk,
                order.tracking_number or "",
                timezone.localtime(order.date).strftime("%Y-%m-%d %H:%M"),
                order.get_channel_display(),
                _csv_safe(order.customer.name),
                order.get_order_status_display(),
                order.get_payment_method_display(),
                order.get_payment_status_display(),
                order.total_payment,
                "Ya" if counted else "Tidak",
            ]
        )
    return response


def _csv_safe(value):
    """Cegah formula injection saat CSV dibuka di spreadsheet."""
    value = str(value or "")
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


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
                filter=Q(grooming_jobs__status__in=WORK_DONE_STATUSES),
                distinct=True,
            ),
        )
        .order_by("first_name", "username")
    )
    context = {
        "active_tab": request.GET.get("tab", "employee"),
        "employee": list(employees.filter(approval=Approval.APPROVED)),
        "pending_staff": User.objects.filter(
            role__in=STAFF_ROLES, approval=Approval.PENDING
        ).select_related("courier_profile").order_by("date_joined"),
        "customers": Customer.objects.order_by("first_name", "last_name"),
        "staff_roles": _assignable_roles(request.user),
    }
    return render(request, "account/manage_account.html", context)


def _assignable_roles(actor):
    return [(code, Role(code).label) for code in STAFF_ROLES if actor.can_manage(code)]


@roleRequired(Role.ADMIN)
def decide_staff(request, pk):
    """Setujui / tolak staf yang mendaftar sendiri."""
    if request.method != "POST":
        return redirect(f"{reverse('manage_account')}?tab=approval")
    staff = get_object_or_404(User, pk=pk, role__in=STAFF_ROLES)
    approve = request.POST.get("decision") == "approve"
    if not request.user.can_manage(staff.role):
        messages.error(request, _("Hanya Super Admin yang bisa memproses akun tingkat admin."))
    elif request.user.decide_registration(staff, approve):
        from store.models import ActivityLog

        ActivityLog.record(staff, "Pendaftaran disetujui" if approve else "Pendaftaran ditolak", request.user)
        messages.success(
            request,
            f"{staff.name} {'disetujui dan sekarang bisa masuk' if approve else 'ditolak'}.",
        )
    else:
        messages.error(request, _("Pendaftaran ini sudah diproses."))
    return redirect(f"{reverse('manage_account')}?tab=approval")


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
            done=Count("pk", filter=Q(status__in=WORK_DONE_STATUSES)),
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
            "staff_roles": _assignable_roles(request.user),
            "can_manage": request.user.can_manage(emp.role),
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
    orders = Order.objects.filter(customer=customer).exclude(
        order_status=OrderStatus.CANCELLED
    )
    total_orders = orders.count()
    # Hanya order lunas yang dihitung sebagai belanja (sama dengan dasbor admin).
    total_spent = (
        orders.filter(payment_status=PaymentStatus.PAID).aggregate(
            total=Sum("total_payment")
        )["total"]
        or 0
    )
    stats = [
        {"value": total_orders, "label": "Total Pesanan"},
        {
            "value": f"Rp {total_spent:,.0f}".replace(",", "."),
            "label": "Total Belanja (lunas)",
        },
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
        form = EmployeeForm(request.POST, actor=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Karyawan berhasil ditambahkan."))
        else:
            _flash_form_errors(request, form)
    return redirect("manage_account")


@roleRequired(Role.ADMIN)
def delete_employee(request, pk):
    back = _next_url(request, reverse("manage_account"))
    if request.method == "POST":
        employee = get_object_or_404(User, pk=pk, role__in=STAFF_ROLES)
        if employee == request.user:
            messages.error(request, _("Kamu tidak bisa menghapus akunmu sendiri."))
            return redirect(back)
        if not request.user.can_manage(employee.role):
            messages.error(request, _("Hanya Super Admin yang bisa menghapus akun Admin."))
            return redirect(back)
        try:
            employee.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Karyawan '{employee.username}' tidak bisa dihapus karena sudah punya riwayat order/layanan.",
            )
            return redirect(back)
        messages.success(request, _("Karyawan berhasil dihapus."))
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
            messages.success(request, _("Pelanggan berhasil ditambahkan."))
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def edit_employee(request, pk):
    employee = get_object_or_404(User, pk=pk, role__in=STAFF_ROLES)
    originalRole = employee.role
    back = _next_url(request, reverse("manage_account"))
    if request.method == "POST":
        if employee != request.user and not request.user.can_manage(originalRole):
            messages.error(request, _("Hanya Super Admin yang bisa mengubah akun Admin."))
            return redirect(back)
        form = EmployeeForm(request.POST, instance=employee, actor=request.user)
        if form.is_valid():
            if employee == request.user and form.cleaned_data["role"] != originalRole:
                messages.error(
                    request, _("Kamu tidak bisa mengubah peran akunmu sendiri.")
                )
                return redirect(back)
            form.save()
            if employee == request.user and form.cleaned_data.get("password"):
                # set_password mengubah hash sesi; tanpa ini admin ter-logout sendiri.
                update_session_auth_hash(request, employee)
            messages.success(request, _("Data karyawan berhasil diperbarui."))
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
            messages.success(request, _("Data pelanggan berhasil diperbarui."))
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def delete_customer(request, pk):
    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=pk)
        try:
            customer.delete()
            messages.success(request, _("Pelanggan berhasil dihapus."))
        except ProtectedError:
            messages.error(
                request,
                f"Pelanggan '{customer.name}' tidak bisa dihapus karena sudah punya riwayat order/booking.",
            )
    return _customer_tab()
