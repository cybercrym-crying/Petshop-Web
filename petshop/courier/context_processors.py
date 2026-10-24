from account.models import Role


def ready_to_pick(courier):
    """Paket yang sudah dikemas dan siap diambil kurir ini (miliknya atau belum ada kurirnya)."""
    from django.db.models import Q

    from transaction.models import Order, OrderStatus

    ready = Order.objects.filter(
        Q(courier=courier) | Q(courier__isnull=True),
        order_status=OrderStatus.CONFIRMED,
        packing_seq__isnull=False,
    )
    return sum(1 for o in ready if o.is_ready_to_ship)


def courier_counts(request):
    """Angka di menu kurir: paket siap diambil di toko dan tugas antar-jemput hewan."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role != Role.COURIER:
        return {}
    from service.models import ServiceBooking

    profile = getattr(user, "courier_profile", None)
    return {
        "ck_ready_count": ready_to_pick(user),
        "ck_pet_count": ServiceBooking.pet_tasks(user).count() if profile and profile.can_carry_pets else 0,
    }
