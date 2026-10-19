from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from account.decorators import roleRequired
from account.models import Role
from transaction.models import Order, OrderStatus


@roleRequired(Role.COURIER)
def dashboard(request):
    q = (request.GET.get("q") or "").strip()
    orders = (
        Order.objects.filter(courier=request.user)
        .select_related("customer", "admin", "courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )

    if q:
        filters = Q(customer__name__icontains=q)
        if q.isdigit():
            filters |= Q(pk=int(q))
        orders = orders.filter(filters)

    active_orders = orders.filter(
        order_status__in=[OrderStatus.CONFIRMED, OrderStatus.ON_DELIVERY]
    )
    delivered_orders = orders.filter(order_status=OrderStatus.DELIVERED)

    return render(
        request,
        "courier/dashboard.html",
        {
            "q": q,
            "active_orders": active_orders,
            "delivered_orders": delivered_orders,
            "total_active": active_orders.count(),
            "total_delivered": delivered_orders.count(),
        },
    )


@roleRequired(Role.COURIER)
def history(request):
    history_orders = (
        Order.objects.filter(courier=request.user)
        .select_related("customer", "admin")
        .prefetch_related("details__product")
        .order_by("-date")
    )

    return render(
        request,
        "courier/history.html",
        {"history_orders": history_orders},
    )


@roleRequired(Role.COURIER)
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer", "admin", "courier").prefetch_related(
            "details__product"
        ),
        pk=pk,
        courier=request.user,
    )
    return render(request, "courier/order_detail.html", {"order": order})


@roleRequired(Role.COURIER)
def update_status(request, pk):
    if request.method != "POST":
        return redirect("courier:dashboard")

    order = get_object_or_404(Order.objects.select_for_update(), pk=pk, courier=request.user)
    action = request.POST.get("action")

    if action == "on_delivery":
        order.mark_on_delivery(request.user)
        messages.success(request, f"Order #{order.pk} sedang dikirim.")
    elif action == "delivered":
        order.mark_delivered()
        messages.success(request, f"Order #{order.pk} berhasil dikirim.")
    else:
        messages.error(request, "Aksi tidak tersedia.")

    return redirect("courier:dashboard")
