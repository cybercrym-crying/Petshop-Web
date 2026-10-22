/*
 * Bagikan lokasi kurir secara langsung memakai Geolocation API (HTML5).
 * - watchPosition() membaca GPS HP; lokasi dikirim ke server tiap ±15 detik
 *   (lebih cepat bila kurir sudah bergerak > 25 m).
 * - Pilihan "sedang membagikan" diingat di localStorage, jadi saat kurir pindah
 *   halaman (dasbor <-> detail order) pengiriman lokasi otomatis lanjut.
 * - Screen Wake Lock dipakai bila tersedia supaya layar tidak mati
 *   (browser HP berhenti membaca GPS ketika layar terkunci / tab di belakang).
 * - Server menolak (409) bila tidak ada paket yang diantar; berbagi otomatis berhenti.
 */
(function () {
  "use strict";

  var panel = document.querySelector("[data-live-location]");
  if (!panel) return;

  var KEY = "courierShareLocation";
  var SEND_EVERY = 15000;
  var MIN_GAP = 5000;
  var MIN_MOVE_METERS = 25;

  var url = panel.getAttribute("data-url");
  var csrf = panel.getAttribute("data-csrf");
  var statusEl = panel.querySelector("[data-live-status]");
  var metaEl = panel.querySelector("[data-live-meta]");
  var button = panel.querySelector("[data-live-toggle]");
  var buttonText = button.querySelector("span");

  var watchId = null;
  var heartbeat = null;
  var wakeLock = null;
  var lastPos = null;
  var lastSentPos = null;
  var lastSentAt = 0;
  var sending = false;

  function remember(on) {
    try {
      localStorage.setItem(KEY, on ? "1" : "0");
    } catch (e) {}
  }

  function remembered() {
    try {
      return localStorage.getItem(KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  function setState(state, text) {
    panel.setAttribute("data-state", state);
    statusEl.textContent = text;
    var active = watchId !== null;
    buttonText.textContent = active ? "Berhenti bagikan" : "Mulai bagikan";
  }

  function setMeta(text) {
    metaEl.hidden = !text;
    metaEl.textContent = text || "";
  }

  function clock(date) {
    return date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function distance(a, b) {
    var R = 6371000;
    var toRad = Math.PI / 180;
    var dLat = (b.latitude - a.latitude) * toRad;
    var dLng = (b.longitude - a.longitude) * toRad;
    var h =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(a.latitude * toRad) * Math.cos(b.latitude * toRad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function send(pos) {
    if (sending) return;
    sending = true;
    var body = new FormData();
    body.append("lat", pos.coords.latitude.toFixed(6));
    body.append("lng", pos.coords.longitude.toFixed(6));
    body.append("accuracy", Math.round(pos.coords.accuracy || 0));
    fetch(url, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { status: response.status, ok: response.ok, data: data };
          });
      })
      .then(function (result) {
        if (result.status === 409) {
          stop();
          setState("off", result.data.message || "Tidak ada paket yang sedang diantar.");
          return;
        }
        if (!result.ok) throw new Error("HTTP " + result.status);
        lastSentAt = Date.now();
        lastSentPos = pos.coords;
        var count = result.data.active_orders || 0;
        setState("on", "Lokasi aktif dibagikan ke " + count + " pelanggan.");
        setMeta(
          "Terakhir terkirim " + clock(new Date()) + " · akurasi ±" + Math.round(pos.coords.accuracy || 0) + " m"
        );
      })
      .catch(function () {
        setState("warn", "Gagal mengirim lokasi (sinyal lemah?). Mencoba lagi otomatis…");
      })
      .then(function () {
        sending = false;
      });
  }

  function onPosition(pos) {
    lastPos = pos;
    var now = Date.now();
    var moved = lastSentPos ? distance(lastSentPos, pos.coords) : Infinity;
    if (now - lastSentAt >= SEND_EVERY || (moved >= MIN_MOVE_METERS && now - lastSentAt >= MIN_GAP)) {
      send(pos);
    }
  }

  function onError(err) {
    if (err.code === 1) {
      stop();
      setState(
        "error",
        "Izin lokasi ditolak. Izinkan akses lokasi untuk situs ini di pengaturan browser, lalu tekan Mulai bagikan."
      );
    } else if (err.code === 2) {
      setState("warn", "GPS belum mendapat posisi. Pastikan GPS/Lokasi HP menyala.");
    } else {
      setState("warn", "Menunggu sinyal GPS…");
    }
  }

  function requestWakeLock() {
    if (!("wakeLock" in navigator) || watchId === null) return;
    navigator.wakeLock
      .request("screen")
      .then(function (lock) {
        wakeLock = lock;
      })
      .catch(function () {});
  }

  function start() {
    if (!("geolocation" in navigator)) {
      setState("error", "Browser ini tidak mendukung lokasi (Geolocation).");
      return;
    }
    if (!window.isSecureContext) {
      setState("error", "Lokasi hanya bisa dibagikan lewat HTTPS. Buka situs dengan alamat https://.");
      return;
    }
    watchId = navigator.geolocation.watchPosition(onPosition, onError, {
      enableHighAccuracy: true,
      maximumAge: 10000,
      timeout: 30000,
    });
    remember(true);
    setState("wait", "Mencari posisi GPS…");
    heartbeat = window.setInterval(function () {
      // Saat kurir berhenti (lampu merah, menunggu pembeli) watchPosition bisa diam;
      // kirim ulang posisi terakhir supaya pelanggan tahu lokasinya masih aktif.
      if (lastPos && Date.now() - lastSentAt >= SEND_EVERY) send(lastPos);
    }, SEND_EVERY);
    requestWakeLock();
  }

  function stop() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    if (heartbeat) window.clearInterval(heartbeat);
    heartbeat = null;
    if (wakeLock) wakeLock.release().catch(function () {});
    wakeLock = null;
    remember(false);
  }

  button.addEventListener("click", function () {
    if (watchId !== null) {
      stop();
      setMeta("");
      setState("off", "Berbagi lokasi dihentikan.");
    } else {
      start();
    }
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      requestWakeLock();
      if (lastPos && watchId !== null && Date.now() - lastSentAt >= SEND_EVERY) send(lastPos);
    }
  });

  if (remembered()) start();
})();
