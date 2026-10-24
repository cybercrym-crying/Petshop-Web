/*
 * Peta rute kurir (Leaflet + OSM): posisi kurir realtime dari gps_guard.js,
 * pin bernomor sesuai urutan antar, garis rute, dan tujuan berikutnya disorot.
 * Daftar titik diambil ulang dari /staff/courier/rute.json tiap 30 detik.
 */
(function () {
  "use strict";

  var el = document.querySelector("[data-route-map]");
  if (!el || !window.L) return;

  var start = [parseFloat(el.getAttribute("data-start-lat")), parseFloat(el.getAttribute("data-start-lng"))];
  var map = L.map(el, { zoomControl: true }).setView(start, 14);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  var me = L.marker(start, {
    icon: L.divIcon({ className: "route-me", html: '<span><i class="bi bi-scooter"></i></span>', iconSize: [40, 40], iconAnchor: [20, 20] }),
    zIndexOffset: 1000,
  }).addTo(map).bindTooltip("Posisi Anda");
  var accuracy = L.circle(start, { radius: 0, color: "#7c3aed", weight: 1, fillOpacity: 0.08 }).addTo(map);
  var line = L.polyline([], { color: "#a78bfa", weight: 4, opacity: 0.9, dashArray: "8 8" }).addTo(map);
  var nextLine = L.polyline([], { color: "#7c3aed", weight: 5, opacity: 0.95 }).addTo(map);
  var stopsLayer = L.layerGroup().addTo(map);
  var storeMarker = null;
  var stops = [];
  var fitted = false;
  var current = start;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function drawLines() {
    var pts = [current];
    stops.forEach(function (s) { if (s.lat !== null) pts.push([s.lat, s.lng]); });
    line.setLatLngs(pts);
    nextLine.setLatLngs(pts.length > 1 ? [pts[0], pts[1]] : []);
  }

  function render(data) {
    stops = data.stops || [];
    stopsLayer.clearLayers();
    if (data.store && !storeMarker) {
      storeMarker = L.marker([data.store.lat, data.store.lng], {
        icon: L.divIcon({ className: "route-store", html: '<span><i class="bi bi-shop"></i></span>', iconSize: [30, 30], iconAnchor: [15, 15] }),
      }).addTo(map).bindTooltip("Toko");
    }
    var bounds = L.latLngBounds([current]);
    stops.forEach(function (s, i) {
      if (s.lat === null) return;
      var isNext = i === 0;
      var m = L.marker([s.lat, s.lng], {
        icon: L.divIcon({
          className: "route-pin" + (isNext ? " is-next" : ""),
          html: "<span>" + s.n + "</span>",
          iconSize: isNext ? [36, 36] : [30, 30],
          iconAnchor: isNext ? [18, 18] : [15, 15],
        }),
        zIndexOffset: isNext ? 800 : 0,
      });
      m.bindPopup(
        "<b>" + s.n + ". " + escapeHtml(s.name) + "</b><br>" + escapeHtml(s.address) +
        "<br>±" + s.km + " km · ±" + s.eta + " menit" + (s.cod ? "<br><b>COD</b>" : "") +
        '<br><a href="' + s.handover_url + '">Serahkan paket</a>'
      );
      m.addTo(stopsLayer);
      bounds.extend([s.lat, s.lng]);
    });
    drawLines();
    if (!fitted && stops.length) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
      fitted = true;
    }
  }

  function load() {
    fetch(el.getAttribute("data-url"), { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { if (data) render(data); })
      .catch(function () {});
  }

  document.addEventListener("gps:update", function (e) {
    current = [e.detail.lat, e.detail.lng];
    me.setLatLng(current);
    accuracy.setLatLng(current).setRadius(Math.min(e.detail.accuracy || 0, 200));
    drawLines();
  });

  load();
  window.setInterval(function () { if (document.visibilityState === "visible") load(); }, 30000);
  window.setTimeout(function () { map.invalidateSize(); }, 100);
})();
