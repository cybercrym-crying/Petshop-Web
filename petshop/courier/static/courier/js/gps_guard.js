function tr(text, vars) {
  return window.petT ? window.petT(text, vars) : text;
}

(function () {
  "use strict";

  var root = document.querySelector("[data-gps-guard]");
  if (!root) return;

  var url = root.getAttribute("data-url");
  var csrf = root.getAttribute("data-csrf");
  var staleMs = (parseInt(root.getAttribute("data-stale"), 10) || 120) * 1000;
  var lock = document.querySelector("[data-gps-lock]");
  var lockText = lock && lock.querySelector("[data-gps-lock-text]");
  var retry = lock && lock.querySelector("[data-gps-retry]");
  var badge = document.querySelector("[data-gps-badge]");

  var SEND_EVERY = 15000;
  var GRACE = 12000; // waktu tunggu posisi pertama sebelum layar dikunci
  var KEY = "courierGpsFix";
  var startedAt = Date.now();
  var denied = false;
  var MIN_GAP = 5000;
  var MIN_MOVE = 25;
  var watchId = null;
  var lastFixAt = 0;
  var lastPos = null;
  var lastSentAt = 0;
  var lastSent = null;
  var wakeLock = null;

  function saveFix(c) {
    try {
      localStorage.setItem(
        KEY,
        JSON.stringify({
          lat: c.latitude,
          lng: c.longitude,
          acc: c.accuracy || 0,
          at: Date.now(),
        }),
      );
    } catch (e) {
      /* mode privat: abaikan */
    }
  }
  function loadFix() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY));
      if (v && typeof v.lat === "number" && Date.now() - v.at < staleMs)
        return v;
    } catch (e) {
      /* abaikan */
    }
    return null;
  }
  function fresh() {
    return lastFixAt && Date.now() - lastFixAt < staleMs;
  }

  function setLocked(locked, text) {
    document.documentElement.classList.toggle("gps-locked", locked);
    if (lock) lock.hidden = !locked;
    if (lockText && text) lockText.textContent = text;
    if (badge) {
      badge.classList.toggle("is-off", locked);
      badge.classList.remove("is-wait");
      badge.textContent = locked ? tr("GPS mati") : tr("GPS aktif");
    }
    document.querySelectorAll("[data-needs-gps]").forEach(function (el) {
      el.disabled = locked;
      el.setAttribute("aria-disabled", locked ? "true" : "false");
    });
  }

  function meters(a, b) {
    var R = 6371000,
      r = Math.PI / 180;
    var dLat = (b.latitude - a.latitude) * r,
      dLng = (b.longitude - a.longitude) * r;
    var h =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(a.latitude * r) *
        Math.cos(b.latitude * r) *
        Math.sin(dLng / 2) *
        Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function send(pos) {
    var body = new FormData();
    body.append("lat", pos.coords.latitude.toFixed(6));
    body.append("lng", pos.coords.longitude.toFixed(6));
    body.append("accuracy", Math.round(pos.coords.accuracy || 0));
    lastSentAt = Date.now();
    lastSent = pos.coords;
    fetch(url, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
    }).catch(function () {});
  }

  function fill(lat, lng, accuracy) {
    document.querySelectorAll("[data-gps-lat]").forEach(function (el) {
      el.value = lat.toFixed(6);
    });
    document.querySelectorAll("[data-gps-lng]").forEach(function (el) {
      el.value = lng.toFixed(6);
    });
    document.dispatchEvent(
      new CustomEvent("gps:update", {
        detail: { lat: lat, lng: lng, accuracy: accuracy },
      }),
    );
  }

  function onPosition(pos) {
    lastPos = pos;
    lastFixAt = Date.now();
    denied = false;
    saveFix(pos.coords);
    setLocked(false);
    fill(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy);
    var now = Date.now();
    var moved = lastSent ? meters(lastSent, pos.coords) : Infinity;
    if (
      now - lastSentAt >= SEND_EVERY ||
      (moved >= MIN_MOVE && now - lastSentAt >= MIN_GAP)
    )
      send(pos);
  }

  function lockDenied() {
    denied = true;
    try {
      localStorage.removeItem(KEY);
    } catch (e) {
      /* abaikan */
    }
    setLocked(
      true,
      tr(
        "Izin lokasi ditolak. Buka pengaturan browser > Izin situs > Lokasi, pilih Izinkan, lalu tekan Coba lagi.",
      ),
    );
  }

  function onError(err) {
    if (err.code === 1) {
      lockDenied();
      return;
    }
    // Timeout / sinyal lemah sesaat: selama posisi terakhir masih segar atau masa tunggu
    // awal belum habis, jangan kunci layar. Pemeriksaan berkala di bawah yang memutuskan.
    if (fresh() || Date.now() - startedAt < GRACE) return;
    setLocked(
      true,
      tr(
        "GPS belum mendapat posisi. Nyalakan Lokasi/GPS di HP lalu tunggu beberapa detik.",
      ),
    );
  }

  function start() {
    if (!("geolocation" in navigator)) {
      setLocked(
        true,
        tr(
          "Browser ini tidak mendukung GPS. Gunakan Chrome atau Safari terbaru.",
        ),
      );
      return;
    }
    if (!window.isSecureContext) {
      setLocked(
        true,
        tr(
          "GPS hanya bisa dipakai lewat HTTPS. Buka situs dengan alamat https://.",
        ),
      );
      return;
    }
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = navigator.geolocation.watchPosition(onPosition, onError, {
      // maximumAge: posisi yang baru diambil halaman sebelumnya boleh dipakai lagi,
      // jadi pindah halaman langsung dapat posisi tanpa menunggu satelit.
      enableHighAccuracy: true,
      maximumAge: 30000,
      timeout: 30000,
    });
    if ("wakeLock" in navigator) {
      navigator.wakeLock
        .request("screen")
        .then(function (l) {
          wakeLock = l;
        })
        .catch(function () {});
    }
  }

  // Posisi tidak diperbarui terlalu lama = GPS dianggap mati.
  window.setInterval(function () {
    if (denied) return;
    if (lastFixAt && Date.now() - lastFixAt > staleMs) {
      setLocked(
        true,
        tr(
          "Sinyal GPS hilang lebih dari {n} detik. Pastikan Lokasi HP menyala.",
          { n: Math.round(staleMs / 1000) },
        ),
      );
    } else if (!lastFixAt && Date.now() - startedAt > GRACE) {
      setLocked(
        true,
        tr(
          "GPS belum mendapat posisi. Nyalakan Lokasi/GPS di HP lalu tunggu beberapa detik.",
        ),
      );
    }
    if (lastPos && Date.now() - lastSentAt >= SEND_EVERY) send(lastPos);
  }, 5000);

  if (retry) retry.addEventListener("click", start);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") start();
  });
  // Awal halaman: pakai posisi terakhir (dari halaman sebelumnya) bila masih segar,
  // supaya layar tidak terkunci sesaat setiap kali pindah halaman.
  var cached = loadFix();
  if (cached) {
    lastFixAt = cached.at;
    setLocked(false);
    fill(cached.lat, cached.lng, cached.acc);
  } else if (badge) {
    badge.classList.remove("is-off");
    badge.classList.add("is-wait");
    badge.textContent = tr("Mencari posisi GPS…");
  }
  // Izin sudah ditolak: kunci langsung tanpa menunggu.
  if (navigator.permissions && navigator.permissions.query) {
    navigator.permissions
      .query({ name: "geolocation" })
      .then(function (st) {
        if (st.state === "denied") lockDenied();
        st.onchange = function () {
          if (st.state === "denied") lockDenied();
          else start();
        };
      })
      .catch(function () {});
  }
  start();
})();
