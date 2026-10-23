/* Tinggi batang grafik dari data-pct (tanpa inline style di template). */
(function () {
  "use strict";
  document.querySelectorAll(".dash-bar__fill[data-pct]").forEach(function (bar) {
    var pct = Math.max(0, Math.min(100, parseInt(bar.dataset.pct, 10) || 0));
    bar.style.height = (pct ? Math.max(pct, 2) : 0) + "%";
  });
})();
