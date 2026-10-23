/*
 * Papan antrean check-in: isi lebar bilah progres dari data-progress="selesai/total",
 * dan muat ulang halaman tiap 60 detik selama kasir tidak sedang memproses check-in.
 */
(function () {
  "use strict";

  Array.prototype.forEach.call(document.querySelectorAll("[data-progress]"), function (bar) {
    var parts = bar.getAttribute("data-progress").split("/");
    var done = parseInt(parts[0], 10) || 0;
    var total = parseInt(parts[1], 10) || 0;
    bar.style.width = total ? Math.round((done / total) * 100) + "%" : "0%";
  });

  var busy = document.querySelector(".ci-booking");
  if (busy) return;
  window.setInterval(function () {
    var typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    var scanning = document.querySelector("[data-qr-video]:not([hidden])");
    if (document.visibilityState === "visible" && !typing && !scanning) window.location.reload();
  }, 60000);
})();
