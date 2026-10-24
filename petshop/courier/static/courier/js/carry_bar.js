/* Bilah muatan kurir: isi lebar dari data-carry="dibawa/maks". */
document.querySelectorAll("[data-carry]").forEach(function (bar) {
  var parts = bar.getAttribute("data-carry").split("/");
  var n = parseInt(parts[0], 10) || 0, max = parseInt(parts[1], 10) || 0;
  var fill = bar.querySelector("i");
  if (fill) fill.style.width = (max ? Math.min(100, n / max * 100) : 0) + "%";
});
