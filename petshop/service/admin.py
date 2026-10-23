from django.contrib import admin

from .models import BookingStep, Pet, Service, ServiceBooking, ServiceStep


class ServiceStepInline(admin.TabularInline):
    model = ServiceStep
    extra = 0


class BookingStepInline(admin.TabularInline):
    model = BookingStep
    extra = 0
    readonly_fields = ("position", "name", "needs_photo", "photo", "note", "done_at", "done_by")
    can_delete = False


@admin.register(Pet)
class PetAdmin(admin.ModelAdmin):
    list_display = ("name", "pet_type", "breed", "owner", "is_active")
    list_filter = ("pet_type", "is_active")
    search_fields = ("name", "owner__first_name", "owner__phone_number")
    raw_id_fields = ("owner",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    inlines = [ServiceStepInline]
    list_display = ("name", "pet_type", "price", "duration_minutes", "is_active")
    list_filter = ("is_active", "pet_type")
    search_fields = ("name",)


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ("pk", "customer", "pet_name", "service", "schedule", "groomer", "status")
    list_filter = ("status", "service")
    search_fields = ("pet_name", "customer__first_name", "customer__last_name", "customer__phone_number")
    raw_id_fields = ("customer", "groomer", "created_by", "pet", "pet_courier", "confirmed_by", "checked_in_by")
    inlines = [BookingStepInline]
