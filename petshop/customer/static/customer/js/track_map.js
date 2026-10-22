/*
 * Peta posisi kurir di halaman Lacak Pesanan.
 * Peta: Leaflet + ubin OpenStreetMap (gratis, tanpa API key).
 * Data: /lacak/<resi>/lokasi/ (JSON) diambil ulang tiap ±15 detik selama tab terbuka.
 */
(function () {
  "use strict";

  var box = document.querySelector("[data-track-live]");
  if (!box || !window.L) return;

  var url = box.getAttribute("data-url");
  var courierName = box.getAttribute("data-courier") || "Kurir";
  var mapEl = box.querySelector("#track-map");
  var emptyEl = box.querySelector("[data-live-empty]");
  var updatedEl = box.querySelector("[data-live-updated]");
  var gmapsEl = box.querySelector("[data-live-gmaps]");

  var map = null;
  var marker = null;
  var accuracy = null;
  var trail = null;
  var lastAt = null;
  var stale = false;
  var pollMs = 15000;
  var timer = null;
  var fitted = false;

  var courierIcon = L.divIcon({
    className: "track-courier-icon",
    html: '<span><i class="fas fa-motorcycle" aria-hidden="true"></i></span>',
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });

  function ensureMap(latlng) {
    if (map) return;
    mapEl.hidden = false;
    map = L.map(mapEl, { zoomControl: true, scrollWheelZoom: false }).setView(latlng, 16);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      // Server ubin OSM menolak permintaan tanpa header Referer, sedangkan Django
      // default-nya "Referrer-Policy: same-origin" (Referer tidak dikirim ke situs lain).
      // Kirim hanya domain toko (tanpa path berisi resi) ke tile.openstreetmap.org.
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    trail = L.polyline([], { color: "#7e2fb8", weight: 4, opacity: 0.6 }).addTo(map);
    accuracy = L.circle(latlng, { radius: 0, color: "#9b4fcf", weight: 1, fillOpacity: 0.08 }).addTo(map);
    marker = L.marker(latlng, { icon: courierIcon, title: courierName, keyboard: false }).addTo(map);
    marker.bindTooltip(courierName, { direction: "top", offset: [0, -20] });
  }

  function ago(date) {
    var seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
    if (seconds < 10) return "baru saja";
    if (seconds < 60) return seconds + " detik lalu";
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) return minutes + " menit lalu";
    return date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  }

  function renderUpdated() {
    if (!lastAt) return;
    updatedEl.textContent = (stale ? "Sinyal kurir terputus · " : "Diperbarui ") + ago(lastAt);
    box.classList.toggle("is-stale", stale);
  }

  function render(data) {
    if (data.status && data.status !== "DALAM_PENGIRIMAN") {
      // Paket sudah sampai / batal: muat ulang supaya status & bukti foto tampil.
      window.location.reload();
      return;
    }
    if (data.poll) pollMs = data.poll * 1000;
    if (!data.live || !data.last) {
      updatedEl.textContent = "Menunggu lokasi kurir";
      return;
    }
    var latlng = [data.last.lat, data.last.lng];
    ensureMap(latlng);
    emptyEl.hidden = true;
    marker.setLatLng(latlng);
    accuracy.setLatLng(latlng).setRadius(Math.min(data.last.accuracy || 0, 300));
    trail.setLatLngs(data.points || []);
    if (!fitted) {
      if ((data.points || []).length > 1) {
        map.fitBounds(trail.getBounds(), { padding: [30, 30], maxZoom: 17 });
      } else {
        map.setView(latlng, 16);
      }
      fitted = true;
    } else if (!map.getBounds().pad(-0.15).contains(latlng)) {
      map.panTo(latlng);
    }
    lastAt = new Date(data.last.at);
    stale = !!data.stale;
    gmapsEl.href = "https://www.google.com/maps?q=" + data.last.lat + "," + data.last.lng;
    gmapsEl.hidden = false;
    renderUpdated();
  }

  function load() {
    fetch(url, { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (data) render(data);
      })
      .catch(function () {
        updatedEl.textContent = "Gagal memuat lokasi, mencoba lagi…";
      })
      .then(schedule);
  }

  function schedule() {
    window.clearTimeout(timer);
    if (document.visibilityState === "visible") timer = window.setTimeout(load, pollMs);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") load();
    else window.clearTimeout(timer);
  });
  window.setInterval(renderUpdated, 5000);
  load();
})();
