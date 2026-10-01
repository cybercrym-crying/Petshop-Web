from django.urls import path
from . import views

urlpatterns = [
    path("", views.productList, name="product_list"),
    path("catalog", views.productCatalog, name="product_catalog"),
    path("add", views.addNewProduct, name="add_product"),
    path("<int:productId>/price", views.setSellingPrice, name="set_selling_price"),
    path("stock-mutation", views.addStockMutation, name="add_stock_mutation"),
]