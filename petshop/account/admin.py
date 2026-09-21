from django.contrib import admin
from .models import User, Account, Employee, Customer, Pet

admin.site.register(User)
admin.site.register(Employee)
admin.site.register(Customer)
admin.site.register(Pet)
# Register your models here.
