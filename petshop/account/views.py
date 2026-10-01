from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import Customer, Role
from .form import RegisterForm, LoginForm
from .decorators import roleRequired

User = get_user_model()

# Peta role -> nama url dashboard masing-masing, dipakai login_form buat
# redirect otomatis setelah login, dan dipakai lagi kalau butuh link "ke
# dashboard saya" di template manapun.
ROLE_DASHBOARD_URL_NAME = {
    Role.OWNER: "staff_owner_dashboard",
    Role.KASIR: "staff_cashier_dashboard",
    Role.STAF_GUDANG: "staff_warehouse_dashboard",
    Role.GROOMER: "staff_service_dashboard",
    Role.PELANGGAN: "customer_dashboard",
}


def home(request):
    return render(request, "index.html")


def registerForm(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            name = form.cleaned_data.get("name")
            email = form.cleaned_data.get("email")
            phoneNumber = form.cleaned_data.get("phoneNumber")
            address = form.cleaned_data.get("address")

            user = User(username=username, email=email, name=name, role=Role.PELANGGAN)
            user.set_password(password)
            user.save()

            Customer.objects.create(
                user=user, name=name, phoneNumber=phoneNumber, address=address
            )

            login(request, user)
            return redirect("register_success")
    else:
        form = RegisterForm()
    return render(request, "account/register.html", {"form": form})


def registerSuccessView(request):
    return render(request, "account/register_success.html")


def loginForm(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            dashboardUrlName = ROLE_DASHBOARD_URL_NAME.get(user.role)
            if dashboardUrlName:
                return redirect(dashboardUrlName)
            # role tidak dikenali/kosong — fallback aman daripada error None
            return redirect("home")
        else:
            errorMessage = "Invalid Credential"
            form = LoginForm()
            return render(request, "account/login.html", {"error": errorMessage, "form": form})
    else:
        form = LoginForm()
        return render(request, "account/login.html", {"form": form})


def logoutForm(request):
    if request.method == "POST":
        logout(request)
        return redirect("home")
    return redirect("home")


@login_required
def customerDashboard(request):
    return render(request, "customer/dashboard.html", {"username": request.user.username})


# --- Dashboard staff, dipindah ke prefix /staff/ (bukan /admin/) supaya
# tidak bentrok dengan Django admin bawaan yang tetap jalan di /admin/. ---

@roleRequired(Role.OWNER)
def staffOwnerDashboard(request):
    return render(request, "staff/owner/dashboard.html", {"username": request.user.username})


@roleRequired(Role.KASIR)
def staffCashierDashboard(request):
    return render(request, "staff/cashier/dashboard.html", {"username": request.user.username})


@roleRequired(Role.STAF_GUDANG)
def staffWarehouseDashboard(request):
    return render(request, "staff/warehouse/dashboard.html", {"username": request.user.username})


@roleRequired(Role.GROOMER)
def staffServiceDashboard(request):
    return render(request, "staff/service/dashboard.html", {"username": request.user.username})