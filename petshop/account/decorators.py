from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def roleRequired(*allowedRoles):
    def decorator(viewFunc):
        @login_required
        @wraps(viewFunc)
        def wrapper(request, *args, **kwargs):
            allowed = set(allowedRoles)
            if "ADMIN" in allowed:
                allowed.add("SUPERADMIN")  # Super Admin punya semua hak Admin
            if request.user.role not in allowed:
                raise PermissionDenied("Kamu tidak punya akses ke halaman ini.")
            return viewFunc(request, *args, **kwargs)

        return wrapper

    return decorator