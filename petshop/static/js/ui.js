/* Ukuran batang grafik & meter dari data-h / data-w (persen), tanpa inline style di template. */
(function () {
  "use strict";
  function pct(v) { return Math.max(0, Math.min(100, parseInt(v, 10) || 0)); }
  document.querySelectorAll("[data-h]").forEach(function (el) {
    var p = pct(el.getAttribute("data-h"));
    el.style.height = (p ? Math.max(p, 2) : 0) + "%";
  });
  document.querySelectorAll("[data-w]").forEach(function (el) {
    el.style.width = pct(el.getAttribute("data-w")) + "%";
  });
})();
