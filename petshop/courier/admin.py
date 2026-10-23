from django.contrib import admin

from product.admin import ReadOnlyAdmin

from .models import CourierLocation, CourierProfile


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


@admin.register(CourierLocation)
class CourierLocationAdmin(ReadOnlyAdmin):
    list_display = ("courier", "latitude", "longitude", "accuracy", "recorded_at")
    list_filter = ("courier",)
    date_hierarchy = "recorded_at"
