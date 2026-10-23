from django.contrib import admin

from .models import Category, Product, StockMutation

admin.site.register(Category)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Hanya untuk melihat data. Perubahan stok dan order wajib lewat
    halaman staf supaya aturan bisnis (mutasi stok, status) tetap berjalan."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "pet_type", "condition", "purchase_price", "selling_price", "stock", "is_active")
    list_filter = ("category", "pet_type", "condition", "is_active")
    search_fields = ("name", "description")
    readonly_fields = ("stock", "created_at", "updated_at")


@admin.register(StockMutation)
class StockMutationAdmin(ReadOnlyAdmin):
    list_display = ("date", "product", "mutationType", "quantity", "createdBy", "note")
    list_filter = ("mutationType", "product__category")
    search_fields = ("product__name", "note")
    date_hierarchy = "date"
