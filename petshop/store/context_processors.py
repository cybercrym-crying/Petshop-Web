from .models import Notification, StoreSettings


def store(request):
    """Pengaturan toko + jumlah notifikasi belum dibaca, tersedia di semua template."""
    user = getattr(request, "user", None)
    data = {"store": StoreSettings.current(), "unread_notifications": 0, "pending_staff_count": 0}
    if user is not None and user.is_authenticated:
        data["unread_notifications"] = Notification.objects.filter(user=user).unread().count()
        if user.is_admin_level:
            from account.models import Approval, User

            data["pending_staff_count"] = User.objects.filter(approval=Approval.PENDING).count()
    return data
