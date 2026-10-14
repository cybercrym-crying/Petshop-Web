from django.db.models import ProtectedError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import Customer, Role
from .form import CustomerForm, LoginForm, EmployeeForm
from .decorators import roleRequired
from django.contrib import messages
from product.models import Product

User = get_user_model()


def home(request):
    return render(request, "index.html")


def customerForm(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data.get("name")
            phoneNumber = form.cleaned_data.get("phone_number")
            address = form.cleaned_data.get("address")

            Customer.objects.create(
                name=name, phone_number=phoneNumber, address=address
            )

            return redirect("register_success")
    else:
        form = CustomerForm()
    return render(request, "account/register.html", {"form": form})


def loginForm(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(user.dashboard_url_name)
        else:
            errorMessage = "Invalid Credential"
            form = LoginForm()
            return render(
                request, "account/login.html", {"error": errorMessage, "form": form}
            )
    else:
        form = LoginForm()
        return render(request, "account/login.html", {"form": form})


def logoutForm(request):
    if request.method == "POST":
        logout(request)
        return redirect("customer:katalog")
    return redirect("customer:katalog")


def customerDashboard(request):
    return render(
        request, "customer/dashboard.html", {"username": request.user.username}
    )


@roleRequired(Role.ADMIN)
def staff_admin_dashboard(request):
    return render(
        request, "staff/admin/dashboard.html", {"username": request.user.username}
    )


@roleRequired(Role.ADMIN)
def manage_account(request):
    context = {
        "active_tab": request.GET.get("tab", "employee"),
        "employee": User.objects.filter(role__in=[Role.ADMIN, Role.COURIER]),
        "customers": Customer.objects.all(),
    }
    return render(request, "staff/admin/manage_account.html", context)


@roleRequired(Role.ADMIN)
def add_employee(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Add employee success")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    return redirect("manage_account")


@roleRequired(Role.ADMIN)
def delete_employee(request, pk):
    if request.method == "POST":
        employee = get_object_or_404(User, pk=pk)
        if employee == request.user:
            messages.error(request, "You cannot delete your account.")
        else:
            employee.delete()
            messages.success(request, "Delete employee success")
    return redirect("manage_account")


def _customer_tab():
    return redirect(f"{reverse('manage_account')}?tab=customer")


def _flash_form_errors(request, form):
    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, f"{field}: {error}")


@roleRequired(Role.ADMIN)
def add_customer(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Add customer success.")
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def edit_employee(request, pk):
    employee = get_object_or_404(User, pk=pk)
    originalRole = employee.role
    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            if employee == request.user and form.cleaned_data["role"] != originalRole:
                messages.error(request, "You cannot change your account role.")
                return redirect("manage_account")
            form.save()
            messages.success(request, "Edit employee success")
        else:
            messages.error(request, f"Failed to edit employee {form.errors}.")
    return redirect("manage_account")


@roleRequired(Role.ADMIN)
def edit_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Edit customer success.")
        else:
            _flash_form_errors(request, form)
    return _customer_tab()


@roleRequired(Role.ADMIN)
def delete_customer(request, pk):
    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=pk)
        try:
            customer.delete()
            messages.success(request, "Delete customer success")
        except ProtectedError:
            messages.error(
                request,
                f"Customer '{customer.name}' because already have order.",
            )
    return _customer_tab()
