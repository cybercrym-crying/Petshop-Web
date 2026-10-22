from django.urls import path

from . import views

app_name = "chatbot"

urlpatterns = [
    path("chatbot/mulai/", views.start, name="start"),
    path("chatbot/tanya/", views.ask, name="ask"),
    path("staff/admin/faq/", views.manage_faq, name="manage_faq"),
    path("staff/admin/faq/tambah/", views.save_faq, name="add_faq"),
    path("staff/admin/faq/<int:pk>/edit/", views.save_faq, name="edit_faq"),
    path("staff/admin/faq/<int:pk>/hapus/", views.delete_faq, name="delete_faq"),
    path("staff/admin/faq/log/bersihkan/", views.clear_unanswered, name="clear_unanswered"),
]
