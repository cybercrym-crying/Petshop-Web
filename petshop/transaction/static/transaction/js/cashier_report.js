/* Laporan kasir: tooltip angka saat batang grafik disentuh / diarahkan kursor / difokus. */
(function () {
  var chart = document.querySelector(".cr-cols");
  if (!chart) return;
  var tip = document.createElement("div");
  tip.className = "cr-tip";
  tip.hidden = true;
  tip.setAttribute("role", "status");
  chart.appendChild(tip);

  function show(col) {
    var bar = col.querySelector(".cr-col__bar");
    tip.textContent = col.getAttribute("data-tip");
    tip.hidden = false;
    var box = chart.getBoundingClientRect();
    var r = bar.getBoundingClientRect();
    var x = r.left + r.width / 2 - box.left;
    var half = tip.offsetWidth / 2;
    x = Math.max(half, Math.min(box.width - half, x));
    tip.style.left = x + "px";
    tip.style.top = r.top - box.top + "px";
  }
  function hide() { tip.hidden = true; }

  chart.querySelectorAll(".cr-col").forEach(function (col) {
    col.addEventListener("mouseenter", function () { show(col); });
    col.addEventListener("focus", function () { show(col); });
    col.addEventListener("click", function () { show(col); });
  });
  chart.addEventListener("mouseleave", hide);
  chart.addEventListener("focusout", hide);
})();
