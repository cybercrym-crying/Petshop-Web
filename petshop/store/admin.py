from django.contrib import admin

from product.admin import ReadOnlyAdmin

from .models import ActivityLog, BankAccount, Complaint, Notification, StoreSettings


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "whatsapp", "updated_at")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("bank", "number", "holder", "is_active", "order")
    list_editable = ("is_active", "order")


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ("user", "title", "created_at", "read_at")
    search_fields = ("title", "user__username")


@admin.register(ActivityLog)
class ActivityLogAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "content_type", "object_id", "action", "actor", "detail")
    list_filter = ("content_type", "action")
    search_fields = ("action", "detail")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("pk", "customer", "category", "status", "created_at", "handled_by")
    list_filter = ("status", "category")
    raw_id_fields = ("customer", "order", "booking", "handled_by")
