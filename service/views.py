from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from account.decorators import roleRequired
from account.models import POS_ROLES, Role, User, person_search
from customer.views import _site_context
from product.models import PetType

from .forms import BookingForm, FinishForm, ServiceForm, StaffBookingForm
from .models import BookingStatus, InvalidBookingTransition, Service, ServiceBooking

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
    return bookings.filter(cond)


def _flash_errors(request, form):
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else ""
        for error in errors:
            messages.error(request, f"{label}: {error}" if label else error)


def _with_booking(qs):
    return qs.select_related("customer", "service", "groomer")


# ---------------------------------------------------------------------------
# Situs pelanggan: katalog layanan + booking + riwayat booking
# ---------------------------------------------------------------------------


def catalog(request):
    """Daftar jasa layanan hewan + form booking (wajib login sebagai customer)."""
    user = request.user
    is_customer = user.is_authenticated and user.role == Role.CUSTOMER
    initial = {}
    if request.GET.get("layanan", "").isdigit():
        initial["service"] = int(request.GET["layanan"])

    if request.method == "POST":
        if not user.is_authenticated:
            return redirect_to_login(reverse("service:catalog"))
        if not is_customer:
            messages.error(request, "Booking online hanya untuk akun customer.")
            return redirect("service:catalog")
        form = BookingForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                booking = ServiceBooking.book(
                    customer=user,
                    service=data["service"],
                    pet_name=data["pet_name"],
                    pet_type=data["pet_type"],
                    schedule=data["schedule"],
                    note=data["note"],
                    created_by=user,
                )
            except InvalidBookingTransition as e:
                form.add_error("service", str(e))
            else:
                messages.success(
                    request,
                    f"Booking #{booking.pk} berhasil dibuat dan menunggu groomer (status Pending).",
                )
                return redirect("service:my_bookings")
    else:
        form = BookingForm(initial=initial)

    return render(
        request,
        "service/catalog.html",
        _site_context(
            active_page="service",
            services=Service.objects.active(),
            form=form,
            is_customer=is_customer,
        ),
    )


@roleRequired(Role.CUSTOMER)
def my_bookings(request):
    bookings = _with_booking(request.user.service_bookings.all()).order_by("-schedule")
    return render(
        request,
        "service/my_bookings.html",
        _site_context(active_page="service", bookings=bookings),
    )


# ---------------------------------------------------------------------------
# Admin & kasir: booking layanan dan jenis layanan
# ---------------------------------------------------------------------------

STATUS_FILTERS = [
    ("", "Semua"),
    (BookingStatus.PENDING, "Pending"),
    (BookingStatus.PROCESS, "Proses"),
    (BookingStatus.DONE, "Selesai"),
]
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
                )
            except InvalidBookingTransition as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"Booking #{booking.pk} dibuat (Pending).")
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
            messages.success(
                request, f"Booking #{booking.pk} ditugaskan ke {groomer.display_name}."
            )
    back = request.POST.get("back", "")
    return redirect(back if back.startswith("/") and not back.startswith("//") else reverse("service:manage_bookings"))


@roleRequired(Role.ADMIN)
def manage_services(request):
    services = Service.objects.annotate(
        total_bookings=Count("bookings"),
        open_bookings=Count(
            "bookings",
            filter=Q(bookings__status__in=[BookingStatus.PENDING, BookingStatus.PROCESS]),
        ),
    ).order_by("-is_active", "name")
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


# ---------------------------------------------------------------------------
# Groomer
# ---------------------------------------------------------------------------

GROOMER_TABS = {
    "pending": {
        "title": "Menunggu Dikerjakan",
        "icon": "bi-hourglass-split",
        "empty": "Tidak ada booking yang menunggu.",
    },
    "proses": {
        "title": "Sedang Diproses",
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
        # Booking pending yang belum punya groomer bisa diambil siapa saja;
        # yang sudah ditugaskan kasir hanya muncul di groomer tersebut.
        "pending": base.filter(status=BookingStatus.PENDING)
        .filter(Q(groomer__isnull=True) | Q(groomer=user))
        .order_by("schedule"),
        "proses": base.filter(status=BookingStatus.PROCESS, groomer=user).order_by(
            "started_at"
        ),
        "selesai": base.filter(status=BookingStatus.DONE, groomer=user).order_by(
            "-finished_at"
        ),
    }


@roleRequired(Role.GROOMER)
def groomer_dashboard(request):
    tab = request.GET.get("status", "pending")
    if tab not in GROOMER_TABS:
        tab = "pending"
    q = request.GET.get("q", "").strip()
    sets = _groomer_querysets(request.user)
    current = _search(sets[tab], q)
    if tab == "selesai":
        current = current[:DONE_LIMIT]
    return render(
        request,
        "service/groomer_dashboard.html",
        {
            "tab": tab,
            "q": q,
            "meta": GROOMER_TABS[tab],
            "bookings": list(current),
            "counts": {key: qs.count() for key, qs in sets.items()},
            "done_limit": DONE_LIMIT,
        },
    )


def _groomer_booking(user, pk, lock=False):
    qs = ServiceBooking.objects.select_for_update() if lock else _with_booking(ServiceBooking.objects.all())
    return get_object_or_404(
        qs.filter(
            Q(groomer=user) | Q(groomer__isnull=True, status=BookingStatus.PENDING)
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
                status=BookingStatus.DONE,
            )
        )
        .exclude(pk=booking.pk)
        .order_by("-finished_at")[:5]
    )
    return render(
        request,
        "service/groomer_booking_detail.html",
        {"booking": booking, "history": history, "finish_form": FinishForm()},
    )


@roleRequired(Role.GROOMER)
def groomer_update_status(request, pk):
    if request.method != "POST":
        return redirect("service:groomer_dashboard")
    action = request.POST.get("action")
    next_tab = "pending"
    try:
        with transaction.atomic():
            booking = _groomer_booking(request.user, pk, lock=True)
            if action == "start":
                booking.start(request.user)
                next_tab = "proses"
                messages.success(request, f"Booking #{booking.pk} sedang diproses.")
            elif action == "finish":
                form = FinishForm(request.POST)
                note = form.cleaned_data["note"] if form.is_valid() else ""
                booking.finish(request.user, note=note)
                next_tab = "selesai"
                messages.success(request, f"Booking #{booking.pk} selesai.")
            else:
                messages.error(request, "Aksi tidak dikenal.")
    except InvalidBookingTransition as e:
        messages.error(request, str(e))
    if request.POST.get("from") == "detail":
        return redirect("service:groomer_booking_detail", pk=pk)
    return redirect(f"{reverse('service:groomer_dashboard')}?status={next_tab}")
