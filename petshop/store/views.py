from django.utils.translation import gettext as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from account.decorators import roleRequired
from account.models import POS_ROLES, Role
from common.exceptions import PetshopError

from .forms import BankAccountFormSet, ComplaintForm, ComplaintResponseForm, StoreSettingsForm
from .models import (
    ActivityLog,
    BankAccount,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Notification,
    StoreSettings,
)


@roleRequired(Role.ADMIN)
def store_settings(request):
    """Pengaturan Toko: alamat & titik peta, jam, WhatsApp, rekening, tarif (Admin & Super Admin)."""
    store = StoreSettings.current()
    form = StoreSettingsForm(request.POST or None, request.FILES or None, instance=store)
    banks = BankAccountFormSet(
        request.POST or None, queryset=BankAccount.objects.all(), prefix="bank"
    )
    if request.method == "POST":
        if form.is_valid() and banks.is_valid():
            with transaction.atomic():
                store = form.save(commit=False)
                store.updated_by = request.user
                store.save()
                saved = banks.save(commit=False)
                for obj in banks.deleted_objects:
                    obj.delete()
                for position, obj in enumerate(saved):
                    obj.order = obj.order or position
                    obj.save()
                ActivityLog.record(store, "Pengaturan toko diubah", actor=request.user,
                                   detail=", ".join(form.changed_data)[:255])
            messages.success(request, _("Pengaturan toko disimpan."))
            return redirect("store:settings")
        messages.error(request, _("Periksa kembali isian yang ditandai merah."))
    return render(
        request,
        "store/settings.html",
        {"form": form, "banks": banks, "store": store, "example_fee": StoreSettings.current().shipping_fee(7)},
    )


def _notification_template(user):
    if user.role == Role.CUSTOMER:
        return "store/notifications_customer.html"
    return "store/notifications_staff.html"


@login_required
def notifications(request):
    items = Notification.objects.filter(user=request.user)[:100]
    return render(request, _notification_template(request.user), {"items": items})


@login_required
def open_notification(request, pk):
    """Tandai dibaca lalu buka halaman tujuan notifikasi."""
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    if note.read_at is None:
        note.read_at = timezone.now()
        note.save(update_fields=["read_at"])
    target = note.url
    if not target or not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect("store:notifications")
    return redirect(target)


@login_required
@require_POST
def read_all_notifications(request):
    Notification.objects.filter(user=request.user).unread().update(read_at=timezone.now())
    messages.success(request, _("Semua notifikasi ditandai sudah dibaca."))
    return redirect("store:notifications")


# ---------------------------------------------------------------------------
# Komplain & ulasan
# ---------------------------------------------------------------------------


@roleRequired(Role.CUSTOMER)
def complaints(request):
    """Pelanggan mengajukan komplain (dengan foto) dan melihat balasan toko."""
    initial = {}
    for key, field in (("pesanan", "order"), ("order", "order"), ("booking", "booking")):
        if request.GET.get(key, "").isdigit():
            initial[field] = int(request.GET[key])
    if "booking" in initial:
        initial["category"] = ComplaintCategory.SERVICE
    form = ComplaintForm(request.POST or None, request.FILES or None, customer=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        complaint = form.save(commit=False)
        complaint.customer = request.user
        complaint.save()
        if complaint.order_id:
            ActivityLog.record(complaint.order, "Komplain diajukan", actor=request.user, detail=f"Komplain #{complaint.pk}")
        if complaint.booking_id:
            ActivityLog.record(complaint.booking, "Komplain diajukan", actor=request.user, detail=f"Komplain #{complaint.pk}")
        Notification.to_staff(
            POS_ROLES, f"Komplain baru #{complaint.pk} · {complaint.get_category_display()}",
            complaint.message[:200], reverse("store:staff_complaint", args=[complaint.pk]),
        )
        messages.success(request, f"Komplain #{complaint.pk} terkirim. Admin akan membalas lewat notifikasi.")
        return redirect("store:complaints")
    mine = request.user.complaints.select_related("order", "booking", "handled_by")
    return render(request, "store/complaints_customer.html", {"form": form, "complaints": mine})


@roleRequired(*POS_ROLES)
def staff_complaints(request):
    status = request.GET.get("status", ComplaintStatus.OPEN)
    rows = Complaint.objects.select_related("customer", "order", "booking", "handled_by")
    counts = dict(Complaint.objects.values_list("status").annotate(n=Count("pk")))
    if status in ComplaintStatus.values:
        rows = rows.filter(status=status)
    else:
        status = ""
    complaints = list(rows[:200])
    selected = None
    picked = request.GET.get("id", "")
    if picked.isdigit():
        selected = Complaint.objects.select_related("customer", "order", "booking").filter(pk=int(picked)).first()
    elif complaints:
        selected = complaints[0]
    return render(
        request,
        "store/complaints_staff.html",
        {
            "complaints": complaints,
            "complaint": selected,
            "form": _complaint_form(selected) if selected else None,
            "related_log": _complaint_log(selected) if selected else [],
            "status": status,
            "filters": [{"code": c, "label": label, "count": counts.get(c, 0)} for c, label in ComplaintStatus.choices]
            + [{"code": "", "label": "Semua", "count": sum(counts.values())}],
        },
    )


@roleRequired(*POS_ROLES)
def staff_complaint(request, pk):
    complaint = get_object_or_404(Complaint.objects.select_related("customer", "order", "booking"), pk=pk)
    form = _complaint_form(complaint, request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            complaint.respond(request.user, form.cleaned_data["status"], form.cleaned_data["response"])
        except PetshopError as e:
            messages.error(request, str(e))
        else:
            Notification.send(
                complaint.customer, f"Komplain #{complaint.pk}: {complaint.get_status_display()}",
                complaint.response[:200], reverse("store:complaints") + f"#komplain-{complaint.pk}",
            )
            messages.success(request, f"Komplain #{complaint.pk} diperbarui dan pelanggan diberi tahu.")
            return redirect("store:staff_complaints")
    return render(
        request, "store/complaint_detail.html",
        {"complaint": complaint, "form": form, "related_log": _complaint_log(complaint)},
    )


def _complaint_form(complaint, data=None):
    return ComplaintResponseForm(
        data,
        initial={"status": complaint.status if complaint.status != ComplaintStatus.OPEN else ComplaintStatus.IN_PROGRESS,
                 "response": complaint.response},
    )


def _complaint_log(complaint):
    """Riwayat pesanan/booking terkait (bukti foto & lokasi) untuk menilai komplain."""
    if complaint.order_id:
        return ActivityLog.for_object(complaint.order)
    if complaint.booking_id:
        return ActivityLog.for_object(complaint.booking)
    return []


@roleRequired(*POS_ROLES)
def reviews(request):
    """Ulasan pelanggan untuk pesanan dan layanan grooming, beserta rata-ratanya."""
    from service.models import ServiceBooking
    from transaction.models import Order

    orders = Order.objects.filter(rating__isnull=False).select_related("customer", "courier").order_by("-rated_at")
    bookings = ServiceBooking.objects.filter(rating__isnull=False).select_related("customer", "service", "groomer").order_by("-rated_at")
    days = request.GET.get("days", "")
    if days in ("7", "30"):
        since = timezone.now() - timezone.timedelta(days=int(days))
        orders = orders.filter(rated_at__gte=since)
        bookings = bookings.filter(rated_at__gte=since)
    else:
        days = ""
    low = request.GET.get("low") == "1"
    per_groomer = (
        bookings.values("groomer__first_name", "groomer__last_name", "groomer__username")
        .annotate(avg=Avg("rating"), n=Count("pk"))
        .order_by("-avg")
    )
    per_courier = (
        orders.exclude(courier__isnull=True)
        .values("courier__first_name", "courier__last_name", "courier__username")
        .annotate(avg=Avg("rating"), n=Count("pk"))
        .order_by("-avg")
    )
    return render(
        request,
        "store/reviews.html",
        {
            "orders": (orders.filter(rating__lte=2) if low else orders)[:50],
            "bookings": (bookings.filter(rating__lte=2) if low else bookings)[:50],
            "days": days,
            "low": low,
            "periods": [("7", _("7 hari")), ("30", _("30 hari")), ("", _("Semua"))],
            "order_avg": orders.aggregate(a=Avg("rating"), n=Count("pk")),
            "booking_avg": bookings.aggregate(a=Avg("rating"), n=Count("pk")),
            "per_groomer": per_groomer,
            "per_courier": per_courier,
        },
    )
