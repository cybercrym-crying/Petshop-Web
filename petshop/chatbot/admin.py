from django.contrib import admin

from .models import ChatLog, FaqEntry


@admin.register(FaqEntry)
class FaqEntryAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "is_quick", "is_active", "hits")
    list_editable = ("order", "is_quick", "is_active")
    search_fields = ("question", "answer", "keywords")


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    list_display = ("message", "matched", "intent", "created_at")
    list_filter = ("intent",)
    search_fields = ("message",)
