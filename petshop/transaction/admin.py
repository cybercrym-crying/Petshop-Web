from django.contrib import admin

from product.admin import ReadOnlyAdmin

from .models import Order, OrderDetail


class OrderDetailInline(admin.TabularInline):
    model = OrderDetail
    extra = 0
    can_delete = False
    readonly_fields = ("product", "quantity", "unit_price", "subtotal")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = ("pk", "tracking_number", "date", "customer_name", "channel", "order_status", "payment_method", "payment_status", "total_payment", "courier")
    list_filter = ("order_status", "payment_status", "payment_method", "channel")
    search_fields = ("tracking_number", "customer__first_name", "customer__last_name", "customer__phone_number")
    date_hierarchy = "date"
    inlines = [OrderDetailInline]

    @admin.display(description="Pelanggan", ordering="customer__first_name")
    def customer_name(self, obj):
        return obj.customer.name if obj.customer else "-"
