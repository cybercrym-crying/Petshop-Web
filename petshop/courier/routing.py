"""Urutan antar kurir: terdekat dulu (nearest neighbour) lalu dirapikan dengan 2-opt.

Jarak memakai garis lurus (haversine) karena tanpa layanan peta berbayar; untuk
paket dalam satu kota (≤ 10 titik) hasilnya sudah dekat dengan rute jalan.
"""

from store.models import StoreSettings, haversine_km

ROAD_FACTOR = 1.3  # jalan kota rata-rata ±30% lebih panjang dari garis lurus
AVG_SPEED_KMH = 25
MINUTES_PER_STOP = 4  # parkir, serah terima, foto


def _dist(a, b):
    return haversine_km(a[0], a[1], b[0], b[1])


def path_length(start, points):
    total, here = 0.0, start
    for p in points:
        total += _dist(here, p)
        here = p
    return total


def nearest_neighbour(start, points):
    remaining = list(points)
    ordered, here = [], start
    while remaining:
        nxt = min(remaining, key=lambda p: _dist(here, p))
        remaining.remove(nxt)
        ordered.append(nxt)
        here = nxt
    return ordered


def two_opt(start, points):
    """Balik potongan rute selama itu memperpendek jalur terbuka (titik awal tetap)."""
    best = list(points)
    improved = True
    while improved and len(best) > 2:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if path_length(start, candidate) + 1e-9 < path_length(start, best):
                    best = candidate
                    improved = True
    return best


def plan(start, points):
    """start: (lat, lng); points: list (lat, lng, key). Kembalikan points terurut."""
    return two_opt(start, nearest_neighbour(start, points))


def eta_minutes(km, stops=0):
    return round(km * ROAD_FACTOR / AVG_SPEED_KMH * 60 + stops * MINUTES_PER_STOP)


def courier_start(courier):
    from .models import CourierLocation

    last = CourierLocation.latest_for(courier)
    if last:
        return (float(last.latitude), float(last.longitude))
    return StoreSettings.current().location


def reroute(courier, start=None):
    """Hitung ulang urutan semua paket yang sedang dibawa kurir; simpan di Order.route_position."""
    from transaction.models import Order, OrderStatus

    start = start or courier_start(courier)
    orders = list(Order.objects.filter(courier=courier, order_status=OrderStatus.ON_DELIVERY))
    with_pin = [o for o in orders if o.has_pin]
    without_pin = sorted((o for o in orders if not o.has_pin), key=lambda o: o.pk)
    points = [(float(o.delivery_latitude), float(o.delivery_longitude), o.pk) for o in with_pin]
    ordered = [p[2] for p in plan(start, points)] + [o.pk for o in without_pin]
    for position, pk in enumerate(ordered, start=1):
        Order.objects.filter(pk=pk).update(route_position=position)
    return ordered


def route_for(courier):
    """Paket yang dibawa kurir, urut rute, dengan jarak & ETA kumulatif dari posisi kurir."""
    from transaction.models import Order, OrderStatus

    start = courier_start(courier)
    orders = list(
        Order.objects.filter(courier=courier, order_status=OrderStatus.ON_DELIVERY)
        .select_related("customer")
        .order_by("route_position", "pk")
    )
    here, km = start, 0.0
    for n, order in enumerate(orders):
        if order.has_pin:
            point = (float(order.delivery_latitude), float(order.delivery_longitude))
            order.leg_km = _dist(here, point)
            km += order.leg_km
            here = point
        else:
            order.leg_km = None
        order.cum_km = km
        order.eta = eta_minutes(km, n)
    return start, orders
