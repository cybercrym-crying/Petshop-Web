from account.models import POS_ROLES


def pending_online_orders(request):
    """Jumlah pesanan online yang menunggu konfirmasi (badge di sidebar staf)."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role not in POS_ROLES:
        return {}
    from .models import Order, OrderStatus

    return {
        "pending_online_orders": Order.objects.filter(
            order_status=OrderStatus.PENDING
        ).count()
    }
