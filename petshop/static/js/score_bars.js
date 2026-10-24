/* Bilah nilai ulasan: isi lebar dari data-score (skala 1-5). */
document.querySelectorAll("[data-score]").forEach(function (bar) {
  var score = parseFloat(String(bar.getAttribute("data-score")).replace(",", ".")) || 0;
  var fill = bar.querySelector("i");
  if (fill) fill.style.width = Math.max(0, Math.min(100, score / 5 * 100)) + "%";
});
