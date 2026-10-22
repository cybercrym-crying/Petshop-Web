from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("account.urls")),
    path("", include("product.urls")),
    path("", include("transaction.urls")),
    path("", include("courier.urls")),
    path("", include("service.urls")),
    path("", include("chatbot.urls")),
    # Alamat lama situs customer (/customer/...) dialihkan permanen ke alamat baru (/...).
    path("customer/", RedirectView.as_view(url="/", permanent=True, query_string=True)),
    path(
        "customer/<path:rest>",
        RedirectView.as_view(url="/%(rest)s", permanent=True, query_string=True),
    ),
    # Situs customer (Home, Shop, About, Cart, Checkout) ada di akar.
    path("", include("customer.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
