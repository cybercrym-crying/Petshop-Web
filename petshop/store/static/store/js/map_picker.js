/*
 * Pemilih titik peta (Leaflet + OpenStreetMap). Dipakai di Pengaturan Toko dan saat checkout.
 * Wadah: [data-map-picker]; input angka: [data-map-lat] dan [data-map-lng] di halaman yang sama.
 * Klik peta / geser pin mengisi input; mengetik di input memindahkan pin.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  var box = document.querySelector("[data-map-picker]");
  var latInput = document.querySelector("[data-map-lat]");
  var lngInput = document.querySelector("[data-map-lng]");
  if (!box || !latInput || !lngInput || !window.L) return;

  var fallback = [
    parseFloat(box.getAttribute("data-default-lat")) || -1.2654,
    parseFloat(box.getAttribute("data-default-lng")) || 116.8312,
  ];
  var lat = parseFloat(latInput.value);
  var lng = parseFloat(lngInput.value);
  var hasPoint = !isNaN(lat) && !isNaN(lng);
  var start = hasPoint ? [lat, lng] : fallback;

  var map = L.map(box, { scrollWheelZoom: false }).setView(start, hasPoint ? 16 : 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  var marker = L.marker(start, { draggable: true, keyboard: true, title: tr("Geser untuk memindahkan") });
  if (hasPoint) marker.addTo(map);

  function fill(latlng) {
    latInput.value = latlng.lat.toFixed(6);
    lngInput.value = latlng.lng.toFixed(6);
    latInput.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function place(latlng, zoom) {
    marker.setLatLng(latlng);
    if (!map.hasLayer(marker)) marker.addTo(map);
    if (zoom) map.setView(latlng, zoom);
    fill(L.latLng(latlng));
  }

  map.on("click", function (e) { place(e.latlng); });
  marker.on("dragend", function () { fill(marker.getLatLng()); });

  function fromInputs() {
    var a = parseFloat(latInput.value);
    var b = parseFloat(lngInput.value);
    if (isNaN(a) || isNaN(b)) return;
    marker.setLatLng([a, b]);
    if (!map.hasLayer(marker)) marker.addTo(map);
    map.panTo([a, b]);
  }
  latInput.addEventListener("input", fromInputs);
  lngInput.addEventListener("input", fromInputs);

  var locate = document.querySelector("[data-map-locate]");
  if (locate) {
    if (!("geolocation" in navigator)) {
      locate.hidden = true;
    } else {
      locate.addEventListener("click", function () {
        locate.disabled = true;
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            locate.disabled = false;
            place([pos.coords.latitude, pos.coords.longitude], 17);
          },
          function () {
            locate.disabled = false;
            window.alert(tr("Lokasi tidak bisa dibaca. Izinkan akses lokasi di browser, atau klik titik di peta."));
          },
          { enableHighAccuracy: true, timeout: 15000 }
        );
      });
    }
  }
  window.setTimeout(function () { map.invalidateSize(); }, 100);
})();
