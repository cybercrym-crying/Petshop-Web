from django.shortcuts import render
from django.http import HttpResponse
from django import template
from .models import Account


def home(request):
    list_account = Account.objects.all()
    context = {"list_account": list_account}
    return render(request, "index.html", context)


# Create your views here.
