from django.urls import path
from . import views

app_name = "product"
urlpatterns = [
    path("staff/admin/manage_product/", views.manage_product, name="manage_product"),
    path(
        "staff/admin/manage_product/add_product",
        views.add_product,
        name="add_product",
    ),
    path(
        "staff/admin/manage_product/<int:pk>/edit/",
        views.edit_product,
        name="edit_product",
    ),
    path(
        "staff/admin/manage_product/<int:pk>/delete/",
        views.delete_product,
        name="delete_product",
    ),
    path("catalog", views.productCatalog, name="product_catalog"),
    path("list", views.product_list, name="product_list"),
    path("<int:productId>/price", views.set_selling_price, name="set_selling_price"),
    path("stock-mutation", views.add_stock_mutation, name="add_stock_mutation"),
]
