from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def roleRequired(*allowedRoles):
    def decorator(viewFunc):
        @login_required
        @wraps(viewFunc)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowedRoles:
                raise PermissionDenied("Kamu tidak punya akses ke halaman ini.")
            return viewFunc(request, *args, **kwargs)

        return wrapper

    return decorator