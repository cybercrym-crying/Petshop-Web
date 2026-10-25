from datetime import date, timedelta
from urllib.parse import urlencode

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from account.decorators import roleRequired
from account.models import POS_ROLES, Role, User, person_search
from common.photos import CameraPhotoForm
from customer.views import _site_context
from product.models import PetType
from store.models import ActivityLog, Notification, StoreSettings
from transaction.models import Order, OrderStatus
from transaction.qr import qr_response

from .forms import (
    BookingForm,
    CheckInForm,
    PetForm,
    RatingForm,
    ServiceForm,
    ServiceStepFormSet,
    StaffBookingForm,
    StepForm,
)
from .models import (
    DEFAULT_STEPS,
    OPEN_BOOKING_STATUSES,
    WORK_DONE_STATUSES,
    BookingStatus,
    InvalidBookingTransition,
    Pet,
    Service,
    ServiceBooking,
)
from .notify import booking_event

# ---------------------------------------------------------------------------
# Pencarian bersama
# ---------------------------------------------------------------------------


def _search(bookings, q):
    if not q:
        return bookings
    bookings, cond = person_search(bookings, q, prefix="customer__")
    cond |= Q(pet_name__icontains=q) | Q(service__name__icontains=q)
    digits = q.lstrip("#")
    if digits.isdigit() and len(digits) <= 9:
        cond |= Q(pk=int(digits))
    upper = q.upper()
    if upper.startswith("G-") and upper[2:].isdigit():
        cond |= Q(queue_date=timezone.localdate(), queue_seq=int(upper[2:]))
    return bookings.filter(cond)


def _flash_errors(request, form):
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else ""
        for error in errors:
            messages.error(request, f"{label}: {error}" if label else error)


def _with_booking(qs):
    return qs.select_related("customer", "service", "groomer", "pet", "pet_courier")


def _safe_back(request, default):
    back = request.POST.get("back", "")
    return back if back.startswith("/") and not back.startswith("//") else default


# ---------------------------------------------------------------------------
# Situs pelanggan: katalog layanan + booking + riwayat booking + hewan saya
# ---------------------------------------------------------------------------


def catalog(request):
    """Daftar jasa layanan hewan + form booking (wajib login sebagai customer)."""
    user = request.user
    is_customer = user.is_authenticated and user.role == Role.CUSTOMER
    customer = user if is_customer else None
    initial = {}
    if request.GET.get("layanan", "").isdigit():
        initial["service"] = int(request.GET["layanan"])
    if is_customer:
        initial["address"] = user.address
        if request.GET.get("hewan", "").isdigit():
            initial["pet"] = int(request.GET["hewan"])

    if request.method == "POST":
        if not user.is_authenticated:
            return redirect_to_login(reverse("service:catalog"))
        if not is_customer:
            messages.error(request, _("Booking online hanya untuk akun customer."))
            return redirect("service:catalog")
        form = BookingForm(request.POST, customer=customer)
        if form.is_valid():
            data = form.cleaned_data
            try:
                booking = ServiceBooking.book(
                    customer=user,
                    service=data["service"],
                    pet=data.get("pet"),
                    pet_name=data["pet_name"],
                    pet_type=data["pet_type"],
                    schedule=data["schedule"],
                    note=data["note"],
                    created_by=user,
                    check_capacity=True,
                    pickup=data["pickup"],
                    return_trip=data["return_trip"],
                    location=form.location,
                    address=data["address"],
                    payment_choice=data["payment_choice"],
                )
            except InvalidBookingTransition as e:
                form.add_error("service", str(e))
            else:
                booking_event(booking, "Booking dibuat", actor=user)
                Notification.to_staff(
                    POS_ROLES,
                    f"Booking baru #{booking.pk} menunggu konfirmasi",
                    f"{booking.service.name} · {booking.pet_name} · {timezone.localtime(booking.schedule):%d %b %H:%M}",
                    reverse("service:manage_bookings") + "?status=PENDING",
                )
                messages.success(
                    request,
                    f"Booking #{booking.pk} berhasil dibuat dan menunggu konfirmasi toko.",
                )
                return redirect("service:my_bookings")
    else:
        form = BookingForm(initial=initial, customer=customer)

    return render(
        request,
        "service/catalog.html",
        _site_context(
            active_page="service",
            services=Service.objects.active().prefetch_related("steps"),
            form=form,
            is_customer=is_customer,
            store=StoreSettings.current(),
        ),
    )


@roleRequired(Role.CUSTOMER)
def cancel_my_booking(request, pk):
    if request.method == "POST":
        try:
            with transaction.atomic():
                booking = get_object_or_404(
                    ServiceBooking.objects.select_for_update(),
                    pk=pk,
                    customer=request.user,
                )
                booking.cancel_by_customer(request.user)
        except InvalidBookingTransition as e:
            messages.error(request, str(e))
        else:
            booking_event(booking, "Dibatalkan pelanggan", actor=request.user)
            messages.success(request, f"Booking #{booking.pk} dibatalkan.")
    return redirect("service:my_bookings")


@roleRequired(Role.CUSTOMER)
def my_bookings(request):
    ServiceBooking.cancel_expired()
    bookings = list(
        _with_booking(request.user.service_bookings.all())
        .prefetch_related("steps")
        .order_by("-schedule")
    )
    for b in bookings:
        b.queue_ahead = b.queue_position()
        b.queue_eta = b.queue_eta_minutes()
        b.step_list = list(b.steps.all())
        b.steps_done = sum(1 for s in b.step_list if s.done_at)
    # Tab penyaring: kelompok status yang mudah dipahami pelanggan.
    groups = {
        "mendatang": ("PENDING", "TERJADWAL"),
        "berjalan": ("DIJEMPUT", "ANTRE", "PROSES", "SIAP", "DIANTAR"),
        "selesai": ("SELESAI",),
        "batal": ("BATAL", "TIDAK_DATANG"),
    }
    tab = request.GET.get("tab", "")
    if tab not in groups:
        tab = ""
    tabs = [("", _("Semua"), len(bookings))] + [
        (key, label, sum(1 for b in bookings if b.status in groups[key]))
        for key, label in (
            ("mendatang", _("Akan datang")),
            ("berjalan", _("Berjalan")),
            ("selesai", _("Selesai")),
            ("batal", _("Dibatalkan")),
        )
    ]
    shown = [b for b in bookings if b.status in groups[tab]] if tab else bookings
    return render(
        request,
        "service/my_bookings.html",
        _site_context(active_page="service", bookings=shown, rating_form=RatingForm(), tab=tab, tabs=tabs,
                      store=StoreSettings.current()),
    )


@roleRequired(Role.CUSTOMER)
def booking_qr(request, pk):
    """QR check-in / serah terima hewan (hanya pemilik booking)."""
    booking = get_object_or_404(ServiceBooking, pk=pk, customer=request.user)
    return qr_response(booking.checkin_payload)


@roleRequired(Role.CUSTOMER)
@require_POST
def rate_booking(request, pk):
    booking = get_object_or_404(ServiceBooking, pk=pk, customer=request.user)
    form = RatingForm(request.POST)
    if form.is_valid():
        try:
            booking.rate(request.user, form.cleaned_data["stars"], form.cleaned_data["review"])
        except InvalidBookingTransition as e:
            messages.error(request, str(e))
        else:
            if booking.groomer_id:
                Notification.send(
                    booking.groomer, f"Ulasan {booking.rating}★ untuk booking #{booking.pk}",
                    booking.review, reverse("service:groomer_booking_detail", args=[booking.pk]),
                )
            messages.success(request, _("Terima kasih atas ulasannya!"))
    else:
        _flash_errors(request, form)
    return redirect(reverse("service:my_bookings") + f"#booking-{booking.pk}")


@never_cache
@roleRequired(Role.CUSTOMER)
def booking_location(request, pk):
    """Posisi kurir yang menjemput / mengantar hewan (JSON untuk peta live)."""
    from courier.models import CourierLocation

    booking = get_object_or_404(ServiceBooking, pk=pk, customer=request.user)
    data = {"found": True, "status": booking.status, "live": False, "points": [], "last": None, "stale": False, "poll": 10}
    if booking.in_transport and booking.pet_courier_id and booking.transport_started_at:
        trail = list(
            CourierLocation.objects.filter(
                courier_id=booking.pet_courier_id, recorded_at__gte=booking.transport_started_at
            ).order_by("recorded_at")[:500]
        )
        store = StoreSettings.current()
        data["store"] = {"lat": float(store.latitude), "lng": float(store.longitude), "name": store.name}
        if not trail:
            # Baru berangkat: pakai posisi terakhir kurir (masih segar) sampai ping berikutnya masuk.
            latest = CourierLocation.latest_for(booking.pet_courier)
            if latest and (timezone.now() - latest.recorded_at).total_seconds() <= store.gps_stale_seconds:
                trail = [latest]
        if trail:
            last = trail[-1]
            data.update(
                live=True,
                points=[[float(p.latitude), float(p.longitude)] for p in trail],
                last=last.as_point(),
                stale=(timezone.now() - last.recorded_at).total_seconds() > store.gps_stale_seconds,
            )
        heading_home = booking.status == BookingStatus.RETURNING or not booking.pet_collected_at
        if heading_home and booking.transport_latitude is not None:
            data["destination"] = {"lat": float(booking.transport_latitude), "lng": float(booking.transport_longitude)}
            data["destination_label"] = "alamat Anda"
        else:
            data["destination"] = {"lat": float(store.latitude), "lng": float(store.longitude)}
            data["destination_label"] = "toko"
        if data["last"]:
            from courier.routing import eta_minutes, path_length

            km = path_length((data["last"]["lat"], data["last"]["lng"]), [(data["destination"]["lat"], data["destination"]["lng"])])
            data["distance_km"] = round(km, 2)
            data["eta_minutes"] = eta_minutes(km, 0)
    response = JsonResponse(data)
    response["Cache-Control"] = "private, no-store"
    return response


@roleRequired(Role.CUSTOMER)
def my_pets(request):
    store = StoreSettings.current()
    pets = list(request.user.pets.filter(is_active=True))
    for pet in pets:
        pet.last = pet.last_service()
        pet.due = pet.grooming_due(store.grooming_reminder_days)
    return render(
        request,
        "service/my_pets.html",
        _site_context(active_page="service", pets=pets, reminder_days=store.grooming_reminder_days),
    )


@roleRequired(Role.CUSTOMER)
def edit_pet(request, pk=None):
    pet = get_object_or_404(Pet, pk=pk, owner=request.user, is_active=True) if pk else None
    form = PetForm(request.POST or None, request.FILES or None, instance=pet)
    if request.method == "POST":
        if request.POST.get("action") == "archive" and pet:
            pet.is_active = False
            pet.save(update_fields=["is_active", "updated_at"])
            messages.success(request, f"{pet.name} dihapus dari daftar Hewan Saya. Riwayat booking tetap tersimpan.")
            return redirect("service:my_pets")
        if form.is_valid():
            saved = form.save(commit=False)
            saved.owner = request.user
            saved.save()
            messages.success(request, f"Profil {saved.name} {'diperbarui' if pet else 'ditambahkan'}.")
            return redirect("service:my_pets")
    history = []
    if pet:
        history = list(
            pet.bookings.select_related("service", "groomer").prefetch_related("steps").order_by("-schedule")[:10]
        )
    return render(
        request,
        "service/pet_form.html",
        _site_context(active_page="service", form=form, pet=pet, history=history),
    )


# ---------------------------------------------------------------------------
# Admin & kasir: booking layanan, check-in & antrean, jenis layanan
# ---------------------------------------------------------------------------

MANAGE_LIMIT = 200
CLOSED_STATUSES = (BookingStatus.DONE, BookingStatus.CANCELLED, BookingStatus.NO_SHOW)


def _paid_exists():
    from transaction.models import OrderServiceLine

    return Exists(
        OrderServiceLine.objects.filter(booking=OuterRef("pk")).exclude(order__order_status=OrderStatus.CANCELLED)
    )


def _needs_action_q(now):
    """Booking yang menunggu tindakan kasir: konfirmasi, groomer/kurir kosong, lewat jadwal, siap, atau bukti bayar."""
    early = [BookingStatus.PENDING, BookingStatus.SCHEDULED]
    return (
        Q(status=BookingStatus.PENDING)
        | Q(status__in=early + [BookingStatus.PICKUP, BookingStatus.QUEUED], groomer__isnull=True)
        | (Q(status__in=early + [BookingStatus.READY], pet_courier__isnull=True)
           & (Q(pickup_requested=True) | Q(return_requested=True)))
        | Q(status__in=early, schedule__lt=now)
        | Q(status=BookingStatus.READY)
        | (Q(payment_proof__gt="") & Q(paid=False))
    )


# Kelompok filter halaman booking: (kode, label, saringan).
def _booking_groups(now):
    return [
        ("", _("Semua"), Q()),
        ("aksi", _("Perlu tindakan"), _needs_action_q(now)),
        ("datang", _("Belum datang"), Q(status__in=[BookingStatus.PENDING, BookingStatus.SCHEDULED, BookingStatus.PICKUP])),
        ("toko", _("Di toko"), Q(status__in=[BookingStatus.QUEUED, BookingStatus.PROCESS, BookingStatus.READY])),
        ("antar", _("Antar-jemput"), Q(pickup_requested=True) | Q(return_requested=True)),
        ("tutup", _("Selesai & batal"), Q(status__in=CLOSED_STATUSES)),
    ]


def _booking_steps(b):
    """Tahapan booking untuk panel detail: [(label, state)] dengan state done/now/todo."""
    S = BookingStatus
    order = [S.PENDING, S.SCHEDULED, S.PICKUP, S.QUEUED, S.PROCESS, S.READY, S.RETURNING, S.DONE]
    steps = [(_("Dipesan"), S.PENDING), (_("Konfirmasi"), S.SCHEDULED)]
    if b.pickup_requested:
        steps.append((_("Dijemput"), S.PICKUP))
    steps += [(_("Check-in"), S.QUEUED), (_("Dikerjakan"), S.PROCESS), (_("Siap"), S.READY)]
    if b.return_requested:
        steps.append((_("Diantar"), S.RETURNING))
    steps.append((_("Selesai"), S.DONE))
    if b.status not in order:
        return []
    pos = order.index(b.status)
    rows = []
    for label, code in steps:
        i = order.index(code)
        # "Dikonfirmasi" dicapai saat status Terjadwal; langkah berikutnya sedang berjalan.
        state = "done" if i < pos or (i == pos and code in (S.PENDING, S.SCHEDULED, S.DONE)) else ("now" if i == pos else "todo")
        rows.append((label, state))
    if b.status in (S.PENDING, S.SCHEDULED):
        nxt = next((k for k, (_l, st) in enumerate(rows) if st == "todo"), None)
        if nxt is not None:
            rows[nxt] = (rows[nxt][0], "now")
    return rows


@roleRequired(*POS_ROLES)
def manage_bookings(request):
    ServiceBooking.cancel_expired()
    now = timezone.now()
    today = timezone.localdate()
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if status not in BookingStatus.values:
        status = ""
    try:
        day = date.fromisoformat(request.GET.get("day", ""))
    except ValueError:
        day = today
    # Pencarian dan saringan status lama (tautan notifikasi) berlaku untuk semua tanggal.
    all_dates = bool(q or status)

    base = _with_booking(ServiceBooking.objects.all()).annotate(paid=_paid_exists())
    scoped = base if all_dates else base.filter(schedule__date=day)
    if status:
        scoped = scoped.filter(status=status)
    scoped = _search(scoped, q)

    groups = _booking_groups(now)
    group = request.GET.get("g", "")
    if group not in {code for code, _label, _q in groups}:
        group = ""
    group_q = dict((code, cond) for code, _label, cond in groups)[group]
    bookings = list(scoped.filter(group_q).order_by("schedule" if not all_dates else "-schedule")[:MANAGE_LIMIT])

    selected = None
    picked = request.GET.get("id", "")
    if picked.isdigit():
        selected = base.filter(pk=int(picked)).first()
    if selected is None and bookings:
        needing = set(scoped.filter(_needs_action_q(now)).values_list("pk", flat=True))
        selected = next((b for b in bookings if b.pk in needing), bookings[0])

    strip_start = today - timedelta(days=2)
    day_counts = dict(
        ServiceBooking.objects.filter(schedule__date__gte=strip_start, schedule__date__lte=strip_start + timedelta(days=8))
        .exclude(status__in=[BookingStatus.CANCELLED])
        .values_list("schedule__date").annotate(n=Count("pk"))
    )
    groomer_load = {}
    if selected:
        groomer_load = dict(
            ServiceBooking.objects.filter(
                schedule__date=timezone.localtime(selected.schedule).date(), status__in=OPEN_BOOKING_STATUSES
            ).exclude(pk=selected.pk).values_list("groomer").annotate(n=Count("pk"))
        )
    groomers = list(User.groomers().order_by("first_name", "username"))
    for g in groomers:
        g.load = groomer_load.get(g.pk, 0)
    keep = {"day": "" if all_dates or day == today else day.isoformat(), "q": q, "status": status, "g": group}

    return render(
        request,
        "service/manage_bookings.html",
        {
            "bookings": bookings,
            "selected": selected,
            "steps": _booking_steps(selected) if selected else [],
            "picked": picked.isdigit(),
            "q": q,
            "status": status,
            "status_label": BookingStatus(status).label if status else "",
            "day": day,
            "today": today,
            "all_dates": all_dates,
            "group": group,
            "groups": [
                {"code": code, "label": label, "count": scoped.filter(cond).count()} for code, label, cond in groups
            ],
            "days": [
                {"date": d, "count": day_counts.get(d, 0)}
                for d in (strip_start + timedelta(days=i) for i in range(9))
            ],
            "keep": urlencode({k: v for k, v in keep.items() if v}),
            "keep_no_group": urlencode({k: v for k, v in keep.items() if v and k != "g"}),
            "pending_all": ServiceBooking.objects.filter(status=BookingStatus.PENDING).count(),
            "form": StaffBookingForm(),
            "groomers": groomers,
            "pet_couriers": list(User.pet_couriers().order_by("first_name", "username")),
            "limit": MANAGE_LIMIT,
            "proofs_waiting": list(_booking_proofs_waiting()[:20]),
        },
    )


@roleRequired(*POS_ROLES)
def create_booking(request):
    if request.method == "POST":
        form = StaffBookingForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                booking = ServiceBooking.book(
                    customer=data["customer"],
                    service=data["service"],
                    pet_name=data["pet_name"],
                    pet_type=data["pet_type"],
                    schedule=data["schedule"],
                    note=data["note"],
                    created_by=request.user,
                    groomer=data["groomer"],
                    confirmed=True,
                )
            except InvalidBookingTransition as e:
                messages.error(request, str(e))
            else:
                booking_event(booking, "Booking dibuat kasir", actor=request.user)
                messages.success(request, f"Booking #{booking.pk} dibuat (Terjadwal).")
        else:
            _flash_errors(request, form)
    return redirect("service:manage_bookings")


@roleRequired(*POS_ROLES)
def assign_groomer(request, pk):
    if request.method == "POST":
        groomer = User.groomers().filter(pk=request.POST.get("groomer") or None).first()
        try:
            with transaction.atomic():
                booking = get_object_or_404(
                    ServiceBooking.objects.select_for_update(), pk=pk
                )
                booking.assign_groomer(groomer)
        except InvalidBookingTransition as e:
            messages.error(request, str(e))
        else:
            booking_event(booking, "Groomer ditugaskan", actor=request.user, detail=groomer.display_name)
            Notification.send(
                groomer, f"Booking #{booking.pk} ditugaskan ke Anda",
                f"{booking.service.name} · {booking.pet_name}",
                reverse("service:groomer_booking_detail", args=[booking.pk]),
            )
            messages.success(
                request, f"Booking #{booking.pk} ditugaskan ke {groomer.display_name}."
            )
    return redirect(_safe_back(request, reverse("service:manage_bookings")))


@roleRequired(*POS_ROLES)
def cancel_booking(request, pk):
    if request.method == "POST":
        try:
            with transaction.atomic():
                booking = get_object_or_404(
                    ServiceBooking.objects.select_for_update(), pk=pk
                )
                booking.cancel()
        except InvalidBookingTransition as e:
            messages.error(request, str(e))
        else:
            booking_event(
                booking, "Dibatalkan toko", actor=request.user,
                customer_title=f"Booking #{booking.pk} dibatalkan toko",
                customer_body="Hubungi admin lewat WhatsApp bila ada pertanyaan.",
            )
            messages.success(request, f"Booking #{booking.pk} dibatalkan.")
    return redirect(_safe_back(request, reverse("service:manage_bookings")))


@roleRequired(*POS_ROLES)
@require_POST
def booking_action(request, pk):
    """Aksi meja kasir: konfirmasi, tidak datang, serahkan ke pemilik, tugaskan kurir hewan."""
    action = request.POST.get("action")
    try:
        with transaction.atomic():
            booking = get_object_or_404(ServiceBooking.objects.select_for_update(), pk=pk)
            if action == "confirm":
                booking.confirm(request.user)
                booking_event(
                    booking, "Dikonfirmasi toko", actor=request.user,
                    customer_title=f"Booking #{booking.pk} terjadwal",
                    customer_body=f"{booking.service.name} untuk {booking.pet_name}, {timezone.localtime(booking.schedule):%d %b %H:%M}. Bayar transfer dari Booking Saya atau di kasir saat datang. Tunjukkan QR booking saat tiba.",
                )
                messages.success(request, f"Booking #{booking.pk} dikonfirmasi (Terjadwal).")
            elif action == "no_show":
                booking.mark_no_show()
                booking_event(booking, "Tidak datang", actor=request.user,
                              customer_title=f"Booking #{booking.pk} ditandai tidak datang",
                              customer_body="Silakan booking ulang bila masih membutuhkan layanan.")
                messages.success(request, f"Booking #{booking.pk} ditandai tidak datang.")
            elif action == "handover":
                booking.hand_to_owner()
                booking_event(booking, "Diambil pemilik", actor=request.user,
                              customer_title=f"{booking.pet_name} sudah diambil",
                              customer_body="Terima kasih! Beri ulasan untuk layanan kami.")
                messages.success(request, f"Booking #{booking.pk} selesai, hewan sudah diambil pemilik.")
            elif action == "courier":
                courier = User.pet_couriers().filter(pk=request.POST.get("courier") or None).first()
                booking.assign_pet_courier(courier)
                booking_event(booking, "Kurir hewan ditugaskan", actor=request.user, detail=courier.display_name)
                Notification.send(
                    courier, f"Tugas antar-jemput hewan #{booking.pk}",
                    f"{booking.pet_name} · {booking.transport_address}", reverse("service:courier_pets"),
                )
                messages.success(request, f"{courier.display_name} ditugaskan antar-jemput booking #{booking.pk}.")
            else:
                messages.error(request, _("Aksi tidak dikenal."))
    except InvalidBookingTransition as e:
        messages.error(request, str(e))
    return redirect(_safe_back(request, reverse("service:manage_bookings")))


def _queue_today():
    today = timezone.localdate()
    queued = list(
        _with_booking(ServiceBooking.objects.filter(status=BookingStatus.QUEUED, queue_date=today)).order_by("queue_seq")
    )
    for b in queued:
        b.queue_ahead = b.queue_position()
        b.queue_eta = b.queue_eta_minutes()
    working = list(_with_booking(ServiceBooking.objects.filter(status=BookingStatus.PROCESS)).prefetch_related("steps").order_by("started_at"))
    for b in working:
        b.steps_done, b.steps_total = b.progress()
    ready = list(_with_booking(ServiceBooking.objects.filter(status__in=[BookingStatus.READY, BookingStatus.RETURNING])).order_by("finished_at"))
    return queued, working, ready


@roleRequired(*POS_ROLES)
def check_in(request):
    """Meja depan: scan QR booking -> cek kondisi -> nomor antrean. Juga papan antrean hari ini."""
    code = (request.POST.get("code") or request.GET.get("kode") or "").strip()
    booking = None
    if request.GET.get("booking", "").isdigit():
        booking = _with_booking(ServiceBooking.objects).filter(pk=int(request.GET["booking"])).first()
    elif code:
        booking = ServiceBooking.find_by_code(code)
        if booking is None:
            messages.error(request, _("QR / kode booking tidak ditemukan atau booking sudah selesai."))
    form = CheckInForm()
    if request.method == "POST" and request.POST.get("action") == "checkin":
        form = CheckInForm(request.POST, request.FILES)
        booking = get_object_or_404(ServiceBooking, pk=request.POST.get("booking"))
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    booking = ServiceBooking.objects.select_for_update().get(pk=booking.pk)
                    booking.check_in(request.user, data["weight_kg"], data["condition"], data["photo"])
            except InvalidBookingTransition as e:
                messages.error(request, str(e))
            else:
                ahead = booking.queue_position()
                booking_event(
                    booking, "Check-in", actor=request.user,
                    detail=f"Antrean {booking.queue_label}. {booking.checkin_condition}",
                    customer_title=f"{booking.pet_name} sudah check-in · antrean {booking.queue_label}",
                    customer_body=f"{ahead} hewan di depan, perkiraan mulai ±{booking.queue_eta_minutes()} menit lagi.",
                )
                if booking.groomer_id:
                    Notification.send(booking.groomer, f"{booking.pet_name} masuk antrean {booking.queue_label}",
                                      booking.service.name, reverse("service:groomer_dashboard"))
                messages.success(request, f"{booking.pet_name} masuk antrean {booking.queue_label}.")
                return redirect("service:check_in")
    queued, working, ready = _queue_today()
    upcoming = list(
        _with_booking(
            ServiceBooking.objects.filter(
                status__in=[BookingStatus.PENDING, BookingStatus.SCHEDULED, BookingStatus.PICKUP],
                schedule__date__lte=timezone.localdate(),
            )
        ).order_by("schedule")[:30]
    )
    trip_log = [e for e in ActivityLog.for_object(booking) if e.photo or e.action == "Hewan dijemput kurir"] if booking else []
    return render(
        request,
        "service/check_in.html",
        {
            "booking": booking,
            "trip_log": trip_log,
            "groomers_active": User.groomers().count(),
            "form": form,
            "code": code,
            "queued": queued,
            "working": working,
            "ready": ready,
            "upcoming": upcoming,
        },
    )


@roleRequired(Role.ADMIN)
def manage_services(request):
    services = Service.objects.annotate(
        total_bookings=Count("bookings"),
        open_bookings=Count(
            "bookings",
            filter=Q(bookings__status__in=OPEN_BOOKING_STATUSES),
        ),
        avg_rating=Avg("bookings__rating"),
    ).prefetch_related("steps").order_by("-is_active", "name")
    services = list(services)
    active = sum(1 for s in services if s.is_active)
    return render(
        request,
        "service/manage_services.html",
        {
            "services": services,
            "form": ServiceForm(),
            "pet_types": PetType.choices,
            "default_steps": DEFAULT_STEPS,
            "count_active": active,
            "count_hidden": len(services) - active,
            "count_running": sum(s.open_bookings for s in services),
        },
    )


@roleRequired(Role.ADMIN)
def save_service(request, pk=None):
    if request.method == "POST":
        instance = get_object_or_404(Service, pk=pk) if pk else None
        form = ServiceForm(request.POST, instance=instance)
        if form.is_valid():
            service = form.save()
            if instance is None:
                # Layanan baru langsung diarahkan ke pengaturan tahapan kerjanya.
                messages.success(
                    request,
                    _("Layanan '%(name)s' ditambahkan. Sekarang atur tahapan kerjanya.") % {"name": service.name},
                )
                return redirect("service:service_steps", service.pk)
            messages.success(
                request,
                f"Layanan '{service.name}' diperbarui.",
            )
        else:
            _flash_errors(request, form)
    return redirect("service:manage_services")


@roleRequired(Role.ADMIN)
def service_steps(request, pk):
    """Admin mengatur tahapan kerja (dan wajib foto atau tidak) per layanan."""
    service = get_object_or_404(Service, pk=pk)
    count = service.steps.count()
    formset = ServiceStepFormSet(
        request.POST or None, instance=service, prefix="steps",
        initial=[{"position": count + n} for n in (1, 2)],
    )
    if request.method == "POST" and formset.is_valid():
        formset.save()
        # Rapikan nomor urut 1..n sesuai urutan yang diisi admin.
        for n, step in enumerate(service.steps.order_by("position", "pk"), start=1):
            if step.position != n:
                step.position = n
                step.save(update_fields=["position"])
        ActivityLog.record(service, "Tahapan diubah", actor=request.user,
                           detail=" → ".join(service.step_names()))
        messages.success(request, f"Tahapan '{service.name}' disimpan.")
        return redirect("service:manage_services")
    return render(
        request, "service/service_steps.html",
        {"service": service, "formset": formset, "default_steps": DEFAULT_STEPS},
    )


# ---------------------------------------------------------------------------
# Groomer
# ---------------------------------------------------------------------------

GROOMER_TABS = {
    "antrean": {
        "title": "Antrean Hari Ini",
        "icon": "bi-list-ol",
        "empty": "Belum ada hewan yang check-in. Hewan masuk antrean setelah check-in di meja kasir.",
    },
    "proses": {
        "title": "Sedang Dikerjakan",
        "icon": "bi-scissors",
        "empty": "Belum ada layanan yang sedang Anda kerjakan.",
    },
    "selesai": {
        "title": "Riwayat Selesai",
        "icon": "bi-check2-circle",
        "empty": "Belum ada layanan yang selesai.",
    },
}
DONE_LIMIT = 30


def _groomer_querysets(user):
    base = _with_booking(ServiceBooking.objects.all())
    return {
        # Hewan yang sudah check-in: yang belum punya groomer bisa diambil siapa saja;
        # yang sudah ditugaskan kasir hanya muncul di groomer tersebut.
        "antrean": base.filter(status=BookingStatus.QUEUED)
        .filter(Q(groomer__isnull=True) | Q(groomer=user))
        .order_by("queue_date", "queue_seq"),
        "proses": base.filter(status=BookingStatus.PROCESS, groomer=user).order_by(
            "started_at"
        ),
        "selesai": base.filter(status__in=WORK_DONE_STATUSES, groomer=user).order_by(
            "-finished_at"
        ),
    }


@roleRequired(Role.GROOMER)
def groomer_dashboard(request):
    tab = request.GET.get("status", "antrean")
    if tab not in GROOMER_TABS:
        tab = "antrean"
    q = request.GET.get("q", "").strip()
    sets = _groomer_querysets(request.user)
    current = _search(sets[tab], q)
    if tab == "selesai":
        current = current[:DONE_LIMIT]
    bookings = list(current.prefetch_related("steps"))
    for b in bookings:
        b.steps_done, b.steps_total = b.progress()
        b.next_step_name = next((s.name for s in b.steps.all() if not s.done_at), "")
        b.step_photos = [s.photo for s in b.steps.all() if s.photo][:3]
    upcoming = (
        _with_booking(ServiceBooking.objects.filter(
            Q(groomer__isnull=True) | Q(groomer=request.user),
            status__in=[BookingStatus.PENDING, BookingStatus.SCHEDULED, BookingStatus.PICKUP],
            schedule__date=timezone.localdate(),
        )).order_by("schedule")
    )
    # Pekerjaan yang sedang berjalan selalu ditampilkan paling atas, apa pun tabnya.
    working = sets["proses"].select_related("checked_in_by").prefetch_related("steps__done_by").first()
    working_steps = []
    if working:
        next_step = None
        for step in working.steps.all():
            state = "done" if step.done_at else ("now" if next_step is None else "next")
            if state == "now":
                next_step = step
            working_steps.append({"step": step, "state": state})
        working.next_step_obj = next_step
        working.is_last_step = next_step is not None and working_steps[-1]["step"] == next_step
        working.steps_done = sum(1 for row in working_steps if row["state"] == "done")
    counts = {key: qs.count() for key, qs in sets.items()}
    # Progres hari ini: yang selesai hari ini dibanding semua pekerjaan hari ini.
    done_today = sets["selesai"].filter(finished_at__date=timezone.localdate()).count()
    day_total = done_today + counts["proses"] + counts["antrean"]
    return render(
        request,
        "service/groomer_dashboard.html",
        {
            "working": working,
            "working_steps": working_steps,
            "tab": tab,
            "q": q,
            "meta": GROOMER_TABS[tab],
            "bookings": bookings,
            "counts": counts,
            "done_today": done_today,
            "day_total": day_total,
            "done_pct": round(done_today * 100 / day_total) if day_total else 0,
            "run_pct": round(counts["proses"] * 100 / day_total) if day_total else 0,
            "done_limit": DONE_LIMIT,
            "upcoming": list(upcoming),
        },
    )


def _groomer_booking(user, pk, lock=False):
    qs = ServiceBooking.objects.select_for_update() if lock else _with_booking(ServiceBooking.objects.all())
    return get_object_or_404(
        qs.filter(
            Q(groomer=user) | Q(groomer__isnull=True, status=BookingStatus.QUEUED)
        ),
        pk=pk,
    )


@roleRequired(Role.GROOMER)
def groomer_booking_detail(request, pk):
    booking = _groomer_booking(request.user, pk)
    history = (
        _with_booking(
            ServiceBooking.objects.filter(
                customer=booking.customer,
                pet_name__iexact=booking.pet_name,
                status__in=WORK_DONE_STATUSES,
            )
        )
        .exclude(pk=booking.pk)
        .order_by("-finished_at")[:5]
    )
    steps = list(booking.steps.select_related("done_by"))
    next_step = next((s for s in steps if not s.done_at), None)
    return render(
        request,
        "service/groomer_booking_detail.html",
        {
            "booking": booking,
            "history": history,
            "steps": steps,
            "next_step": next_step,
            "is_last_step": next_step is not None and next_step == steps[-1],
            "log": ActivityLog.for_object(booking),
        },
    )


@roleRequired(Role.GROOMER)
def groomer_update_status(request, pk):
    if request.method != "POST":
        return redirect("service:groomer_dashboard")
    action = request.POST.get("action")
    # Tahap bisa diselesaikan langsung dari kartu "Sedang dikerjakan" di dasbor.
    from_dashboard = request.POST.get("from") == "dashboard"
    next_tab = "antrean"
    try:
        with transaction.atomic():
            booking = _groomer_booking(request.user, pk, lock=True)
            if action == "start":
                booking.start(request.user)
                next_tab = "proses"
                booking_event(
                    booking, "Mulai dikerjakan", actor=request.user,
                    customer_title=f"{booking.pet_name} mulai dikerjakan",
                    customer_body=f"Groomer {request.user.display_name} · ikuti tiap tahap dan fotonya di Booking Saya.",
                )
                messages.success(request, f"Booking #{booking.pk} mulai dikerjakan.")
            elif action == "step":
                next_tab = "proses"
                step_form = StepForm(request.POST, request.FILES, photo_required=False)
                if not step_form.is_valid():
                    for errors in step_form.errors.values():
                        for error in errors:
                            messages.error(request, error)
                    if from_dashboard:
                        return redirect(f"{reverse('service:groomer_dashboard')}?status=proses")
                    return redirect("service:groomer_booking_detail", pk=pk)
                data = step_form.cleaned_data
                step = booking.complete_step(request.user, data["photo"], data["note"])
                booking_event(
                    booking, f"Tahap: {step.name}", actor=request.user, detail=step.note,
                    photo=step.photo or None, lat=data["latitude"], lng=data["longitude"],
                )
                if booking.status == BookingStatus.READY:
                    next_tab = "selesai"
                    title = f"{booking.pet_name} selesai & siap " + ("diantar pulang" if booking.return_requested else "diambil")
                    body = booking.groomer_note or "Lihat foto hasilnya di Booking Saya."
                    if not booking.is_paid:
                        body += (" Selesaikan pembayaran transfer di Booking Saya supaya kurir bisa mengantar pulang."
                                 if booking.return_requested else " Pembayaran di kasir saat mengambil hewan.")
                    booking_event(booking, "Siap diambil", actor=request.user, customer_title=title,
                                  customer_body=body)
                    Notification.to_staff(
                        POS_ROLES, f"Booking #{booking.pk} siap" + (" diantar kurir" if booking.return_requested else " diambil"),
                        booking.pet_name, reverse("service:check_in"),
                    )
                    if booking.return_requested and booking.pet_courier_id and booking.is_paid:
                        Notification.send(booking.pet_courier, f"{booking.pet_name} siap diantar pulang",
                                          booking.transport_address, reverse("service:courier_pets"))
                    messages.success(request, f"Semua tahap selesai. Booking #{booking.pk} siap.")
                else:
                    Notification.send(
                        booking.customer, f"{booking.pet_name}: {step.name} selesai",
                        "Lihat fotonya di Booking Saya.", reverse("service:my_bookings") + f"#booking-{booking.pk}",
                    )
                    messages.success(request, f"Tahap '{step.name}' selesai.")
                    if not from_dashboard:
                        return redirect("service:groomer_booking_detail", pk=pk)
            else:
                messages.error(request, _("Aksi tidak dikenal."))
    except InvalidBookingTransition as e:
        messages.error(request, str(e))
    if request.POST.get("from") == "detail":
        return redirect("service:groomer_booking_detail", pk=pk)
    return redirect(f"{reverse('service:groomer_dashboard')}?status={next_tab}")


# ---------------------------------------------------------------------------
# Kurir: antar-jemput hewan (khusus kurir yang ditandai "Bisa antar-jemput hewan")
# ---------------------------------------------------------------------------


def _gps_ok(request):
    from courier.models import CourierLocation
    from courier.views import GPS_REQUIRED

    if CourierLocation.is_fresh(request.user):
        return True
    messages.error(request, GPS_REQUIRED)
    return False


def _my_pet_trip(request, pk, lock=False):
    qs = ServiceBooking.objects.select_for_update() if lock else _with_booking(ServiceBooking.objects.all())
    return get_object_or_404(qs, pk=pk, pet_courier=request.user)


@roleRequired(Role.COURIER)
def courier_pets(request):
    mine = _with_booking(ServiceBooking.objects.filter(pet_courier=request.user))
    active = list(_with_booking(ServiceBooking.pet_tasks(request.user)).order_by("schedule"))
    done = list(mine.filter(status=BookingStatus.DONE, return_requested=True).order_by("-closed_at")[:10])
    carrying = Order.objects.filter(courier=request.user, order_status=OrderStatus.ON_DELIVERY).count()
    return render(
        request, "service/courier_pets.html", {"active": active, "done": done, "carrying": carrying}
    )


ARRIVED_ACTION = "Tiba di toko"
# Pilihan cepat kondisi hewan saat dijemput (digabung ke catatan riwayat).
PICKUP_CONDITIONS = [_lazy("Sehat"), _lazy("Gelisah"), _lazy("Ada luka"), _lazy("Ada kutu")]


def _condition_detail(request, note):
    """Gabungkan chip kondisi yang dipilih kurir dengan catatannya: 'Kondisi: Sehat, Gelisah. catatan'."""
    allowed = {str(c) for c in PICKUP_CONDITIONS}
    picked = [c for c in request.POST.getlist("condition") if c in allowed]
    parts = []
    if picked:
        parts.append(_("Kondisi: %(list)s.") % {"list": ", ".join(picked)})
    if note:
        parts.append(note)
    return " ".join(parts)[:255]


def _trip_steps(booking):
    """Langkah antar-jemput untuk ditampilkan berurutan: (label, state, waktu). state: done/now/todo."""
    rows = []
    if booking.is_return_leg:
        returning = booking.status in (BookingStatus.RETURNING, BookingStatus.DONE)
        # Antar pulang hanya bisa dimulai setelah lunas, jadi tahap bayar pasti sudah lewat.
        paid = booking.is_paid or returning
        ready = booking.status in (BookingStatus.READY, BookingStatus.RETURNING, BookingStatus.DONE)
        rows.append((_("Hewan selesai dan siap diantar"), "done" if ready else "now", booking.finished_at))
        rows.append((_("Pembayaran lunas"), "done" if paid else ("now" if ready else "todo"), None))
        rows.append((_("Foto hewan, berangkat antar pulang"),
                     "done" if returning else ("now" if ready and paid else "todo"), None))
        rows.append((_("Scan QR di HP pemilik, foto saat diserahkan"),
                     "done" if booking.status == BookingStatus.DONE else ("now" if returning else "todo"),
                     booking.closed_at))
        return rows
    started = booking.status == BookingStatus.PICKUP or booking.checked_in_at is not None
    collected = booking.pet_collected_at is not None
    rows.append((_("Berangkat menjemput"), "done" if started else "now", booking.transport_started_at))
    rows.append((_("Scan QR di HP pemilik, foto hewan saat diterima"),
                 "done" if collected else ("now" if started else "todo"), booking.pet_collected_at))
    rows.append((_("Bawa ke toko, check-in di kasir"),
                 "done" if booking.checked_in_at else ("now" if collected else "todo"), booking.checked_in_at))
    return rows


@roleRequired(Role.COURIER)
@require_POST
def courier_pet_check(request, pk):
    booking = _my_pet_trip(request, pk)
    ok = booking.check_code(request.POST.get("code"))
    return JsonResponse(
        {"ok": ok, "message": "QR cocok. Foto hewannya." if ok else "QR / kode tidak cocok dengan booking ini."},
        status=200 if ok else 400,
    )


@roleRequired(Role.COURIER)
def courier_pet_trip(request, pk):
    """Langkah antar-jemput: berangkat jemput -> scan QR & foto di rumah -> (check-in toko) ->
    foto saat dibawa pulang -> scan QR & foto saat diserahkan."""
    booking = _my_pet_trip(request, pk)
    form = CameraPhotoForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if not _gps_ok(request):
            return redirect("service:courier_pet_trip", pk=pk)
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                booking = _my_pet_trip(request, pk, lock=True)
                if action == "start_pickup":
                    booking.start_pickup(request.user)
                    booking_event(booking, "Kurir berangkat menjemput", actor=request.user,
                                  customer_title=f"Kurir menuju rumah Anda untuk menjemput {booking.pet_name}",
                                  customer_body="Pantau posisinya di Booking Saya. Siapkan QR booking.")
                    messages.success(request, _("Status: menjemput hewan. Hati-hati di jalan."))
                elif form.is_valid():
                    data = form.cleaned_data
                    lat, lng = data["latitude"], data["longitude"]
                    if action == "collect":
                        booking.collect_pet(request.user, request.POST.get("code"), data["photo"])
                        booking_event(booking, "Hewan dijemput kurir", actor=request.user,
                                      detail=_condition_detail(request, data["note"]),
                                      photo=booking.pickup_photo, lat=lat, lng=lng,
                                      customer_title=f"{booking.pet_name} sudah bersama kurir",
                                      customer_body="Sedang dibawa ke toko.")
                        messages.success(request, _("Hewan dijemput. Bawa ke toko untuk check-in di kasir."))
                    elif action == "arrive":
                        booking.check_arrival(request.user)
                        if any(e.action == ARRIVED_ACTION for e in ActivityLog.for_object(booking)):
                            raise InvalidBookingTransition(_("Foto tiba di toko sudah tersimpan."))
                        booking_event(booking, ARRIVED_ACTION, actor=request.user, detail=data["note"],
                                      photo=data["photo"], lat=lat, lng=lng)
                        messages.success(request, _("Foto tiba di toko tersimpan. Serahkan hewan ke kasir."))
                    elif action == "start_return":
                        photo = booking.start_return(request.user, data["photo"])
                        booking_event(booking, "Diantar pulang", actor=request.user, detail=data["note"],
                                      photo=photo, lat=lat, lng=lng,
                                      customer_title=f"{booking.pet_name} sedang diantar pulang",
                                      customer_body="Pantau posisi kurir di Booking Saya. Siapkan QR booking.")
                        messages.success(request, _("Status: mengantar pulang."))
                    elif action == "deliver":
                        booking.deliver_pet(request.user, request.POST.get("code"), data["photo"])
                        booking_event(booking, "Diserahkan ke pemilik", actor=request.user, detail=data["note"],
                                      photo=booking.return_photo, lat=lat, lng=lng,
                                      customer_title=f"{booking.pet_name} sudah sampai di rumah",
                                      customer_body="Terima kasih! Beri ulasan untuk layanan kami.")
                        messages.success(request, _("Selesai, hewan sudah diserahkan ke pemilik."))
                        return redirect("service:courier_pets")
                    else:
                        messages.error(request, _("Aksi tidak dikenal."))
                else:
                    for errors in form.errors.values():
                        for error in errors:
                            messages.error(request, error)
        except InvalidBookingTransition as e:
            messages.error(request, str(e))
        return redirect("service:courier_pet_trip", pk=pk)
    step = None
    if booking.status in (BookingStatus.PENDING, BookingStatus.SCHEDULED) and booking.pickup_requested:
        step = "start_pickup"
    elif booking.status == BookingStatus.PICKUP and not booking.pet_collected_at:
        step = "collect"
    elif booking.status == BookingStatus.READY and booking.return_requested:
        step = "start_return" if booking.is_paid else "wait_payment"
    elif booking.status == BookingStatus.RETURNING:
        step = "deliver"
    log = list(ActivityLog.for_object(booking))
    arrived = any(e.action == ARRIVED_ACTION for e in log)
    if booking.status == BookingStatus.PICKUP and booking.pet_collected_at:
        step = "at_store" if arrived else "arrive"
    return render(
        request,
        "service/courier_pet_trip.html",
        {
            "booking": booking,
            "step": step,
            "trip_steps": _trip_steps(booking),
            "log": log,
            "arrived": arrived,
            "carrying": Order.objects.filter(courier=request.user, order_status=OrderStatus.ON_DELIVERY).count()
            if step == "start_pickup" else 0,
            "conditions": PICKUP_CONDITIONS,
        },
    )


@roleRequired(Role.CUSTOMER)
def booking_payment(request, pk):
    """Bayar transfer booking yang jadwalnya sudah dikonfirmasi: kirim foto bukti, dicek kasir/admin."""
    from customer.forms import PaymentProofForm

    booking = get_object_or_404(_with_booking(ServiceBooking.objects.all()), pk=pk, customer=request.user)
    if not booking.can_pay_transfer:
        if booking.status == BookingStatus.PENDING:
            messages.info(request, _("Tunggu jadwal dikonfirmasi toko dulu, baru bayar."))
        else:
            messages.info(request, f"Booking #{booking.pk} tidak sedang menunggu pembayaran.")
        return redirect(reverse("service:my_bookings") + f"#booking-{booking.pk}")
    form = PaymentProofForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            booking.submit_payment_proof(request.user, form.cleaned_data["photo"])
        except InvalidBookingTransition as error:
            messages.error(request, str(error))
        else:
            booking_event(booking, "Bukti transfer dikirim", actor=request.user,
                          detail=form.cleaned_data.get("note", ""))
            Notification.to_staff(
                POS_ROLES,
                f"Bukti transfer booking #{booking.pk}",
                f"{request.user.name} · {booking.service.name} · Rp {booking.total_price:,}".replace(",", "."),
                reverse("service:booking_payment_check", args=[booking.pk]),
            )
            messages.success(request, _("Bukti transfer terkirim. Kami kabari begitu pembayaran dicek."))
            return redirect(reverse("service:my_bookings") + f"#booking-{booking.pk}")
    return render(
        request,
        "service/booking_payment.html",
        _site_context(active_page="service", booking=booking, form=form),
    )


def _booking_proofs_waiting():
    return (
        _with_booking(ServiceBooking.objects.exclude(payment_proof="").exclude(payment_proof__isnull=True))
        .filter(payment_lines__isnull=True)
        .order_by("payment_proof_at")
    )


@roleRequired(*POS_ROLES)
def booking_payment_check(request, pk):
    """Cek bukti transfer booking: cocokkan dengan mutasi rekening, lalu setujui (jadi struk transfer) atau tolak."""
    booking = get_object_or_404(_with_booking(ServiceBooking.objects.all()), pk=pk)
    if request.method == "POST":
        decision = request.POST.get("decision")
        try:
            with transaction.atomic():
                booking = ServiceBooking.objects.select_for_update().get(pk=pk)
                if decision == "approve":
                    order = booking.verify_transfer(request.user)
                    booking_event(
                        booking, "Pembayaran transfer diverifikasi", actor=request.user, detail=order.receipt_no,
                        customer_title=f"Pembayaran booking #{booking.pk} diterima",
                        customer_body=f"{booking.service.name} untuk {booking.pet_name} sudah lunas. Tidak perlu bayar lagi di kasir.",
                    )
                    if booking.status == BookingStatus.READY and booking.return_requested and booking.pet_courier_id:
                        Notification.send(booking.pet_courier, f"{booking.pet_name} siap diantar pulang",
                                          booking.transport_address, reverse("service:courier_pets"))
                    messages.success(request, f"Booking #{booking.pk} lunas (struk {order.receipt_no}).")
                elif decision == "reject":
                    note = request.POST.get("note", "")
                    booking.reject_transfer(request.user, note)
                    booking_event(
                        booking, "Bukti transfer ditolak", actor=request.user, detail=note,
                        customer_title=f"Bukti transfer booking #{booking.pk} perlu dikirim ulang",
                        customer_body=note,
                    )
                    messages.warning(request, f"Bukti booking #{booking.pk} ditolak; pelanggan diminta kirim ulang.")
                else:
                    messages.error(request, _("Aksi tidak dikenal."))
        except InvalidBookingTransition as e:
            messages.error(request, str(e))
            return redirect("service:booking_payment_check", pk=pk)
        return redirect(reverse("service:manage_bookings") + "?bayar=cek")
    return render(
        request,
        "service/booking_payment_check.html",
        {"booking": booking, "waiting": list(_booking_proofs_waiting().exclude(pk=booking.pk)[:10])},
    )
