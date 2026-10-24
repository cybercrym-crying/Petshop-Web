/*
 * Gerak halus bersama: kartu muncul bertahap saat masuk layar dan angka besar "menghitung".
 * Dimuat di <head> (atau tepat setelah <body>) lewat partials/_motion.html, sebelum konten
 * tergambar, supaya kartu tidak berkedip. Kalau skrip gagal, kartu tetap tampil (bd-off).
 */
(function () {
  "use strict";
  var root = document.documentElement;
  if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (root.classList.contains("bd-js")) return;  // sudah dimuat
  root.classList.add("bd-js");

  var CARDS = [
    ".ui-card", ".sg-card", ".ad-stat", ".sg-alert", ".gd-card", ".gd-work", ".gd-switch", ".gd-cards > li",
    ".dash-card", ".dash-tile", ".dash-stat", ".acc-card", ".cx-card", ".mo-card", ".co-card", ".track-card",
    ".ab-card", ".value-card", ".pet-card", ".product-card", ".order-card", ".pt-card"
  ].join(",");
  var COUNT = ".ad-hero__big, .ad-stat__n, .sg-big, .ui-kpi__value, .gd-progress__big b, .dash-stat > strong";

  // Pengaman: kalau langkah berikut gagal, jangan biarkan kartu tersembunyi.
  var ok = false;
  setTimeout(function () { if (!ok) root.classList.add("bd-off"); }, 2500);

  function countUp(el) {
    if (el.children.length || el.dataset.counted) return;
    el.dataset.counted = "1";
    var text = el.textContent;
    var m = text.match(/\d[\d.]*/);
    if (!m) return;
    var target = parseInt(m[0].replace(/\./g, ""), 10);
    if (!target || target < 2) return;
    var before = text.slice(0, m.index), after = text.slice(m.index + m[0].length);
    var nf = new Intl.NumberFormat("id-ID");
    var start = null, dur = Math.min(1200, 500 + String(target).length * 90);
    el.setAttribute("aria-label", text.trim());
    function step(t) {
      if (start === null) start = t;
      var p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = before + nf.format(Math.round(target * e)) + after;
      if (p < 1) requestAnimationFrame(step);
      else { el.textContent = text; el.removeAttribute("aria-label"); }
    }
    requestAnimationFrame(step);
  }

  function init() {
    var all = Array.prototype.slice.call(document.querySelectorAll(CARDS));
    var cards = all.filter(function (el) {
      // Kartu di dalam kartu lain ikut induknya; elemen sticky/fixed tidak digeser.
      if (el.parentElement && el.parentElement.closest(CARDS)) return false;
      var pos = getComputedStyle(el).position;
      return pos !== "fixed" && pos !== "sticky";
    });
    var io = new IntersectionObserver(function (entries) {
      var n = 0;
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        io.unobserve(el);
        el.style.transitionDelay = Math.min(n++, 8) * 70 + "ms";
        el.classList.add("is-in");
        el.querySelectorAll(COUNT).forEach(countUp);
        el.addEventListener("transitionend", function done(ev) {
          if (ev.target !== el) return;
          el.removeEventListener("transitionend", done);
          el.classList.remove("bd-reveal", "is-in");
          el.style.transitionDelay = "";
        });
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });
    cards.forEach(function (el) {
      el.classList.add("bd-reveal");
      io.observe(el);
    });
    ok = true;
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
