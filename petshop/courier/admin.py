from django.contrib import admin

from .models import CourierProfile


@admin.register(CourierProfile)
class CourierProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "vehicle", "service_area", "status")
    list_filter = ("status",)
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "service_area",
    )
