from django.utils.translation import gettext as _
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Avg, Count, Q
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
    return render(
        request,
        "service/my_bookings.html",
        _site_context(active_page="service", bookings=bookings, rating_form=RatingForm()),
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

STATUS_FILTERS = [("", "Semua")] + [(code, label) for code, label in BookingStatus.choices]
MANAGE_LIMIT = 200


@roleRequired(*POS_ROLES)
def manage_bookings(request):
    status = request.GET.get("status", "")
    if status not in BookingStatus.values:
        status = ""
    q = request.GET.get("q", "").strip()

    bookings = _with_booking(ServiceBooking.objects.all())
    counts = dict(
        ServiceBooking.objects.values_list("status").annotate(n=Count("pk"))
    )
    if status:
        bookings = bookings.filter(status=status)
    bookings = _search(bookings, q).order_by("-schedule")

    return render(
        request,
        "service/manage_bookings.html",
        {
            "bookings": list(bookings[:MANAGE_LIMIT]),
            "status": status,
            "q": q,
            "status_filters": [
                {
                    "code": code,
                    "label": label,
                    "count": counts.get(code, 0) if code else sum(counts.values()),
                }
                for code, label in STATUS_FILTERS
            ],
            "form": StaffBookingForm(),
            "groomers": list(User.groomers().order_by("first_name", "username")),
            "pet_couriers": list(User.pet_couriers().order_by("first_name", "username")),
            "limit": MANAGE_LIMIT,
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
                    customer_body=f"{booking.service.name} untuk {booking.pet_name}, {timezone.localtime(booking.schedule):%d %b %H:%M}. Tunjukkan QR booking saat tiba.",
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
    return render(
        request,
        "service/check_in.html",
        {
            "booking": booking,
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
    return render(
        request,
        "service/manage_services.html",
        {"services": services, "form": ServiceForm(), "pet_types": PetType.choices},
    )


@roleRequired(Role.ADMIN)
def save_service(request, pk=None):
    if request.method == "POST":
        instance = get_object_or_404(Service, pk=pk) if pk else None
        form = ServiceForm(request.POST, instance=instance)
        if form.is_valid():
            service = form.save()
            messages.success(
                request,
                f"Layanan '{service.name}' {'diperbarui' if instance else 'ditambahkan'}.",
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
    return render(request, "service/service_steps.html", {"service": service, "formset": formset})


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
    upcoming = (
        _with_booking(ServiceBooking.objects.filter(
            Q(groomer__isnull=True) | Q(groomer=request.user),
            status__in=[BookingStatus.PENDING, BookingStatus.SCHEDULED, BookingStatus.PICKUP],
            schedule__date=timezone.localdate(),
        )).order_by("schedule")
    )
    # Pekerjaan yang sedang berjalan selalu ditampilkan paling atas, apa pun tabnya.
    working = sets["proses"].prefetch_related("steps").first()
    working_steps = []
    if working:
        next_step = None
        for step in working.steps.all():
            state = "done" if step.done_at else ("now" if next_step is None else "next")
            if state == "now":
                next_step = step
            working_steps.append({"step": step, "state": state})
        working.next_step_obj = next_step
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
            "counts": {key: qs.count() for key, qs in sets.items()},
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
                step_form = StepForm(request.POST, request.FILES, photo_required=False)
                if not step_form.is_valid():
                    for errors in step_form.errors.values():
                        for error in errors:
                            messages.error(request, error)
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
                    booking_event(booking, "Siap diambil", actor=request.user, customer_title=title,
                                  customer_body=booking.groomer_note or "Lihat foto hasilnya di Booking Saya.")
                    Notification.to_staff(
                        POS_ROLES, f"Booking #{booking.pk} siap" + (" diantar kurir" if booking.return_requested else " diambil"),
                        booking.pet_name, reverse("service:check_in"),
                    )
                    if booking.return_requested and booking.pet_courier_id:
                        Notification.send(booking.pet_courier, f"{booking.pet_name} siap diantar pulang",
                                          booking.transport_address, reverse("service:courier_pets"))
                    messages.success(request, f"Semua tahap selesai. Booking #{booking.pk} siap.")
                else:
                    Notification.send(
                        booking.customer, f"{booking.pet_name}: {step.name} selesai",
                        "Lihat fotonya di Booking Saya.", reverse("service:my_bookings") + f"#booking-{booking.pk}",
                    )
                    messages.success(request, f"Tahap '{step.name}' selesai.")
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
    active = list(
        mine.filter(
            Q(status__in=[BookingStatus.PENDING, BookingStatus.SCHEDULED], pickup_requested=True)
            | Q(status=BookingStatus.PICKUP)
            | Q(status__in=[BookingStatus.QUEUED, BookingStatus.PROCESS, BookingStatus.READY], return_requested=True)
            | Q(status=BookingStatus.RETURNING)
        ).order_by("schedule")
    )
    done = list(mine.filter(status=BookingStatus.DONE, return_requested=True).order_by("-closed_at")[:10])
    return render(request, "service/courier_pets.html", {"active": active, "done": done})


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
                        booking_event(booking, "Hewan dijemput kurir", actor=request.user, detail=data["note"],
                                      photo=booking.pickup_photo, lat=lat, lng=lng,
                                      customer_title=f"{booking.pet_name} sudah bersama kurir",
                                      customer_body="Sedang dibawa ke toko.")
                        messages.success(request, _("Hewan dijemput. Bawa ke toko untuk check-in di kasir."))
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
        step = "start_return"
    elif booking.status == BookingStatus.RETURNING:
        step = "deliver"
    return render(
        request,
        "service/courier_pet_trip.html",
        {"booking": booking, "step": step, "log": ActivityLog.for_object(booking)},
    )
