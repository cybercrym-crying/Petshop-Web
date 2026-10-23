from account.models import POS_ROLES, Role


def pending_online_orders(request):
    """Badge sidebar staf: pesanan online baru, bukti transfer yang menunggu dicek, dan antrean packing."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role not in POS_ROLES:
        return {}
    from courier.models import CashRemittance, RemittanceStatus
    from service.models import BookingStatus, ServiceBooking
    from store.models import Complaint, ComplaintStatus

    from .models import Order, OrderStatus, PaymentStatus, ReturnRequest, ReturnStatus

    from .models import CashierShift

    return {
        # Status kasir di menu samping hanya untuk peran Kasir; admin jarang membuka shift.
        "cashier_shift_known": user.role == Role.CASHIER,
        "cashier_shift": CashierShift.current(user) if user.role == Role.CASHIER else None,
        "pending_online_orders": Order.objects.filter(
            order_status=OrderStatus.PENDING
        ).count(),
        "proof_waiting_count": Order.objects.filter(payment_status=PaymentStatus.PENDING)
        .exclude(order_status=OrderStatus.CANCELLED)
        .exclude(payment_proof="")
        .exclude(payment_proof__isnull=True)
        .count(),
        "remittance_count": CashRemittance.objects.filter(status=RemittanceStatus.SUBMITTED).count(),
        "booking_pending_count": ServiceBooking.objects.filter(status=BookingStatus.PENDING).count(),
        "queue_count": ServiceBooking.objects.filter(
            status__in=[BookingStatus.QUEUED, BookingStatus.READY]
        ).count(),
        "complaint_open_count": Complaint.objects.filter(status=ComplaintStatus.OPEN).count(),
        "to_pack_count": Order.objects.filter(
            order_status=OrderStatus.CONFIRMED, packing_seq__isnull=False, packed_at__isnull=True
        ).count(),
        "pending_return_count": ReturnRequest.objects.filter(status=ReturnStatus.PENDING).count(),
    }
