from django.contrib import admin

from .models import Service, ServiceBooking


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "pet_type", "price", "duration_minutes", "is_active")
    list_filter = ("is_active", "pet_type")
    search_fields = ("name",)


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ("pk", "customer", "pet_name", "service", "schedule", "groomer", "status")
    list_filter = ("status", "service")
    search_fields = ("pet_name", "customer__first_name", "customer__last_name", "customer__phone_number")
    raw_id_fields = ("customer", "groomer", "created_by")
