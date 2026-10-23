/*
 * Peta posisi kurir (halaman Lacak Pesanan dan Dasbor pelanggan).
 * Peta: Leaflet + ubin OpenStreetMap (gratis, tanpa API key).
 * Data: /lacak/<resi>/lokasi/ (JSON) diambil ulang tiap ±10 detik selama tab terbuka.
 * Antar-jemput hewan memakai komponen yang sama (data-live-status="DIJEMPUT DIANTAR").
 * Setiap elemen [data-track-live] punya peta sendiri, jadi beberapa paket bisa dipantau sekaligus.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  if (!window.L) return;

  var courierIcon = L.divIcon({
    className: "track-courier-icon",
    html: '<span><i class="fas fa-motorcycle" aria-hidden="true"></i></span>',
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
  var homeIcon = L.divIcon({
    className: "track-pin-icon track-pin-icon--home",
    html: '<span><i class="fas fa-house" aria-hidden="true"></i></span>',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
  var storeIcon = L.divIcon({
    className: "track-pin-icon track-pin-icon--store",
    html: '<span><i class="fas fa-store" aria-hidden="true"></i></span>',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });

  function ago(date) {
    var seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
    if (seconds < 10) return tr("baru saja");
    if (seconds < 60) return tr("{n} detik lalu", { n: seconds });
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) return tr("{n} menit lalu", { n: minutes });
    return date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  }

  function LiveTracker(box) {
    this.box = box;
    this.url = box.getAttribute("data-url");
    this.courierName = box.getAttribute("data-courier") || "Kurir";
    this.mapEl = box.querySelector("[data-live-map]");
    this.emptyEl = box.querySelector("[data-live-empty]");
    this.etaEl = box.querySelector("[data-live-eta]");
    this.updatedEl = box.querySelector("[data-live-updated]");
    this.gmapsEl = box.querySelector("[data-live-gmaps]");
    this.map = null;
    this.lastAt = null;
    this.stale = false;
    this.pollMs = 10000;
    this.timer = null;
    this.fitted = false;
  }

  LiveTracker.prototype.ensureMap = function (latlng) {
    if (this.map) return;
    this.mapEl.hidden = false;
    this.map = L.map(this.mapEl, { zoomControl: true, scrollWheelZoom: false }).setView(latlng, 16);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      // Server ubin OSM menolak permintaan tanpa header Referer, sedangkan Django
      // default-nya "Referrer-Policy: same-origin" (Referer tidak dikirim ke situs lain).
      // Kirim hanya domain toko (tanpa path berisi resi) ke tile.openstreetmap.org.
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(this.map);
    this.trail = L.polyline([], { color: "#7e2fb8", weight: 4, opacity: 0.6 }).addTo(this.map);
    this.line = L.polyline([], { color: "#7e2fb8", weight: 2, opacity: 0.7, dashArray: "6 8" }).addTo(this.map);
    // Peta di dalam elemen yang baru tampil perlu dihitung ulang ukurannya.
    var map = this.map;
    window.setTimeout(function () { map.invalidateSize(); }, 50);
  };

  // Penanda kurir dibuat saat lokasi pertama masuk (sebelum itu peta hanya menampilkan toko & alamat).
  LiveTracker.prototype.ensureCourier = function (latlng) {
    if (this.marker) return;
    this.accuracy = L.circle(latlng, { radius: 0, color: "#9b4fcf", weight: 1, fillOpacity: 0.08 }).addTo(this.map);
    this.marker = L.marker(latlng, { icon: courierIcon, title: this.courierName, keyboard: false, zIndexOffset: 500 }).addTo(this.map);
    this.marker.bindTooltip(this.courierName, { direction: "top", offset: [0, -20] });
  };

  // Paket belum diantar: tampilkan rute toko -> alamat agar pelanggan sudah bisa melihat petanya.
  LiveTracker.prototype.renderWaiting = function (data) {
    var points = [];
    if (data.store) points.push([data.store.lat, data.store.lng]);
    if (data.destination && data.destination_label !== "toko") points.push([data.destination.lat, data.destination.lng]);
    if (!points.length) return;
    this.ensureMap(points[0]);
    this.placePins(data);
    this.line.setLatLngs(points.length > 1 ? points : []);
    if (!this.fitted) {
      if (points.length > 1) this.map.fitBounds(L.latLngBounds(points), { padding: [36, 36], maxZoom: 16 });
      else this.map.setView(points[0], 15);
      this.fitted = true;
    }
  };

  LiveTracker.prototype.placePins = function (data) {
    if (data.destination && !this.homeMarker && data.destination_label !== "toko") {
      this.homeMarker = L.marker([data.destination.lat, data.destination.lng], { icon: homeIcon, keyboard: false })
        .addTo(this.map)
        .bindTooltip("Alamat Anda", { direction: "top", offset: [0, -14] });
    }
    if (data.store && !this.storeMarker) {
      this.storeMarker = L.marker([data.store.lat, data.store.lng], { icon: storeIcon, keyboard: false })
        .addTo(this.map)
        .bindTooltip(data.store.name || tr("Toko"), { direction: "top", offset: [0, -14] });
    }
  };

  LiveTracker.prototype.renderUpdated = function () {
    if (!this.lastAt) return;
    this.updatedEl.textContent = (this.stale ? tr("Sinyal GPS kurir terputus · ") : tr("Diperbarui ")) + ago(this.lastAt);
    this.box.classList.toggle("is-stale", this.stale);
  };

  LiveTracker.prototype.renderEta = function (data) {
    if (!this.etaEl) return;
    var parts = [];
    if (typeof data.distance_km === "number") parts.push(tr("Jarak kurir ke {dest} ±{km} km", { dest: tr(data.destination_label || "alamat Anda"), km: data.distance_km.toFixed(1) }));
    if (typeof data.eta_minutes === "number") parts.push(tr("perkiraan tiba ±{n} menit", { n: Math.max(1, data.eta_minutes) }));
    if (typeof data.stops_before === "number") {
      parts.push(data.stops_before === 0 ? tr("Anda tujuan berikutnya") : tr("{n} pengantaran lagi sebelum Anda", { n: data.stops_before }));
    }
    this.etaEl.hidden = parts.length === 0;
    this.etaEl.textContent = parts.join(" · ");
  };

  LiveTracker.prototype.render = function (data) {
    var active = (this.box.getAttribute("data-live-status") || "DALAM_PENGIRIMAN").split(" ");
    var initial = this.box.getAttribute("data-live-initial");
    if (data.status && (active.indexOf(data.status) === -1 || (initial && data.status !== initial))) {
      // Paket/hewan sudah sampai atau batal: muat ulang supaya status & bukti foto tampil.
      window.location.reload();
      return;
    }
    if (data.poll) this.pollMs = data.poll * 1000;
    if (!data.live || !data.last) {
      this.renderWaiting(data);
      this.updatedEl.textContent = data.status === "DALAM_PENGIRIMAN" || !data.status ? tr("Menunggu lokasi kurir") : tr("Menunggu kurir mengambil paket");
      return;
    }
    var latlng = [data.last.lat, data.last.lng];
    this.ensureMap(latlng);
    this.ensureCourier(latlng);
    this.placePins(data);
    this.emptyEl.hidden = true;
    this.marker.setLatLng(latlng);
    this.accuracy.setLatLng(latlng).setRadius(Math.min(data.last.accuracy || 0, 300));
    this.trail.setLatLngs(data.points || []);
    this.line.setLatLngs(data.destination ? [latlng, [data.destination.lat, data.destination.lng]] : []);
    if (!this.fitted) {
      var bounds = L.latLngBounds([latlng]);
      (data.points || []).forEach(function (p) { bounds.extend(p); });
      if (data.destination) bounds.extend([data.destination.lat, data.destination.lng]);
      this.map.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
      this.fitted = true;
    } else if (!this.map.getBounds().pad(-0.15).contains(latlng)) {
      this.map.panTo(latlng);
    }
    this.lastAt = new Date(data.last.at);
    this.stale = !!data.stale;
    this.renderEta(data);
    if (this.gmapsEl) {
      this.gmapsEl.href = "https://www.google.com/maps?q=" + data.last.lat + "," + data.last.lng;
      this.gmapsEl.hidden = false;
    }
    this.renderUpdated();
  };

  LiveTracker.prototype.load = function () {
    var self = this;
    fetch(this.url, { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (data) self.render(data);
      })
      .catch(function () {
        self.updatedEl.textContent = tr("Gagal memuat lokasi, mencoba lagi…");
      })
      .then(function () { self.schedule(); });
  };

  LiveTracker.prototype.schedule = function () {
    window.clearTimeout(this.timer);
    if (document.visibilityState === "visible") {
      this.timer = window.setTimeout(this.load.bind(this), this.pollMs);
    }
  };

  var trackers = Array.prototype.map.call(document.querySelectorAll("[data-track-live]"), function (box) {
    return new LiveTracker(box);
  });
  if (!trackers.length) return;

  document.addEventListener("visibilitychange", function () {
    trackers.forEach(function (t) {
      if (document.visibilityState === "visible") t.load();
      else window.clearTimeout(t.timer);
    });
  });
  window.setInterval(function () {
    trackers.forEach(function (t) { t.renderUpdated(); });
  }, 5000);
  trackers.forEach(function (t) { t.load(); });
})();
