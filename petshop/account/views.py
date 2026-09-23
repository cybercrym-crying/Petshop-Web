from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout  # type: ignore
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django import template
from .models import Employee, Customer
from .form import RegisterForm, LoginForm
from django.contrib.auth import get_user_model

User = get_user_model()


def home(request):
    list_employee = Employee.objects.all()
    context = {"list_employee": list_employee}
    return render(request, "index.html", context)


def register_form(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            name = form.cleaned_data.get("name")
            email = form.cleaned_data.get("email")
            phone_number = form.cleaned_data.get("phone_number")
            user = User(username=username, email=email)  # type: ignore
            user.set_password(password)

            user.save()
            customer = Customer.objects.create(
                user=user, name=name, phone_number=phone_number
            )
            login(request, user)  # type: ignore
            return redirect("register_success")
    else:
        form = RegisterForm()
    context = {"form": form}
    return render(request, "account/register.html", context)


def register_success_view(request):
    return render(request, "account/register_success.html")


def login_form(request):
    print(f"METHOD: {request.method}")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)  # type: ignore
            if hasattr(user, "employee"):
                match user.employee.role:  # type: ignore
                    case "OWNER":
                        return redirect("admin/")
                    case "CASHIER":
                        return redirect("cashier_dashboard")
                    case "WAREHOUSE":
                        return redirect("warehouse_dashboard")
                    case "SERVICE":
                        return redirect("service_dashboard")
            else:
                return redirect("customer_dashboard")
        else:
            error_message = "Invalid Credential"
            form = LoginForm()
            context = {"error": error_message, "form": form}
            return render(request, "account/login.html", context)
    else:
        form = LoginForm()
        return render(request, "account/login.html", {"form": form})


def logout_form(request):
    if request.method == "POST":
        logout(request)
        return redirect("home")
    else:
        return redirect("customer_dashboard")


@login_required
def customer(request):
    username = request.user.username
    return render(request, "customer/dashboard.html", {"username": username})


@login_required
def cashier(request):
    username = request.user.username
    return render(request, "cashier/dashboard.html", {"username": username})


@login_required
def warehouse(request):
    username = request.user.username
    return render(request, "warehouse/dashboard.html", {"username": username})


@login_required
def service(request):
    username = request.user.username
    return render(request, "service/dashboard.html", {"username": username})


# Create your views here.
