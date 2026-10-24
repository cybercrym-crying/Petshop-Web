/* Beranda admin: grafik garis penjualan kasir vs online, tooltip per hari, dan tombol Grafik/Tabel. */
(function () {
  "use strict";
  var card = document.getElementById("ad-trend");
  var box = card && card.querySelector("[data-chart]");
  var src = document.getElementById("ad-trend-data");
  if (!box || !src) return;

  var data = JSON.parse(src.textContent);
  var lang = document.documentElement.lang || "id";
  var NS = "http://www.w3.org/2000/svg";
  var L = box.dataset;
  var nf = new Intl.NumberFormat("id-ID");
  var active = -1;

  data.forEach(function (p) {
    var d = new Date(p.d + "T00:00:00");
    p.t = p.s + p.o;
    p.short = d.toLocaleDateString(lang, { weekday: "short" });
    p.dm = d.getDate() + "/" + (d.getMonth() + 1);
    p.full = d.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "short" });
  });

  function rp(v) { return "Rp " + nf.format(v); }
  function unit(v) {
    if (v >= 1e6) return (v / 1e6).toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " " + L.uMillion;
    if (v >= 1e3) return Math.round(v / 1e3) + " " + L.uThousand;
    return String(v);
  }
  // Langkah sumbu "rapi" (1, 2, 2.5, 5 × 10^k) dengan paling banyak 5 garis.
  function niceStep(max) {
    var raw = max / 4, pow = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    var steps = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * pow >= raw) return steps[i] * pow;
    return 10 * pow;
  }
  function el(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    for (var k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }
  function text(parent, x, y, str, cls, anchor) {
    var t = el("text", { x: x, y: y, "class": cls || "", "text-anchor": anchor || "middle" }, parent);
    t.textContent = str;
    return t;
  }

  var tip = document.createElement("div");
  tip.className = "ad-tip";
  tip.hidden = true;
  tip.setAttribute("role", "status");

  var geo, firstDraw = true;
  function draw() {
    var W = Math.max(box.clientWidth, 280);
    var narrow = W < 520;
    var H = narrow ? 220 : 260, padL = 52, padR = 12, padT = 22, padB = 28;
    var pw = W - padL - padR, ph = H - padT - padB, n = data.length, slot = pw / n;
    var peak = Math.max.apply(null, data.map(function (p) { return Math.max(p.s, p.o); })) || 1;
    var step = niceStep(peak), top = Math.ceil(peak / step) * step;
    var y = function (v) { return padT + ph - (v / top) * ph; };
    var x = function (i) { return padL + slot * i + slot / 2; };
    geo = { W: W, H: H, x: x, y: y, padT: padT, ph: ph, slot: slot };

    box.textContent = "";
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": L.aria, tabindex: "0" }, box);
    for (var v = 0; v <= top + 1; v += step) {
      el("line", { x1: padL, x2: W - padR, y1: y(v), y2: y(v), "class": v ? "ad-grid" : "ad-base" }, svg);
      text(svg, padL - 8, y(v) + 4, v ? unit(v) : "0", "ad-axis", "end");
    }
    var every = Math.ceil(n / (narrow ? 7 : 10));
    data.forEach(function (p, i) {
      if (i % every === 0 || i === n - 1) {
        var lbl = n <= 7 ? (narrow ? p.short : p.short + " " + p.dm) : p.dm;
        text(svg, x(i), H - 8, lbl, "ad-axis");
      }
    });
    var cross = el("line", { x1: 0, x2: 0, y1: padT, y2: padT + ph, "class": "ad-cross" }, svg);
    var dots = n <= 31;
    [["s", "is-store"], ["o", "is-online"]].forEach(function (pair) {
      var d = data.map(function (p, i) { return (i ? "L" : "M") + x(i).toFixed(1) + "," + y(p[pair[0]]).toFixed(1); }).join("");
      el("path", { d: d, pathLength: 1, "class": "ad-line " + pair[1] + (n > 31 ? " is-dense" : "") + (firstDraw ? " is-draw" : "") }, svg);
      if (dots) data.forEach(function (p, i) { el("circle", { cx: x(i), cy: y(p[pair[0]]), r: n <= 14 ? 4.5 : 3, "class": "ad-dot " + pair[1] + (firstDraw ? " is-draw" : "") }, svg); });
    });
    // Satu label langsung: titik tertinggi.
    var best = { i: 0, k: "s", v: -1 };
    data.forEach(function (p, i) { ["s", "o"].forEach(function (k) { if (p[k] > best.v) best = { i: i, k: k, v: p[k] }; }); });
    if (best.v > 0) text(svg, x(best.i), y(best.v) - 11, unit(best.v), "ad-peak" + (firstDraw ? " is-fade" : ""));
    firstDraw = false;  // garis hanya "tergambar" sekali, bukan setiap ubah ukuran
    var hits = el("g", {}, svg);
    data.forEach(function (p, i) {
      var r = el("rect", { x: padL + slot * i, y: padT, width: slot, height: ph, "class": "ad-hit", "data-i": i }, hits);
      r.addEventListener("mouseenter", function () { show(i); });
      r.addEventListener("click", function () { show(i); });
    });
    svg.addEventListener("mouseleave", hide);
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      show(Math.max(0, Math.min(n - 1, (active < 0 ? n - 1 : active + (e.key === "ArrowRight" ? 1 : -1)))));
    });
    svg.addEventListener("focus", function () { if (active < 0) show(n - 1); });
    geo.cross = cross;
    box.appendChild(tip);
  }

  function row(cls, label, value) {
    return '<div class="ad-tip__row"><span>' + (cls ? '<i class="' + cls + '"></i>' : "") + label + "</span><b>" + value + "</b></div>";
  }
  function show(i) {
    var p = data[i];
    active = i;
    tip.innerHTML = "<strong>" + p.full + "</strong>" +
      row("is-store", L.lStore, rp(p.s)) + row("is-online", L.lOnline, rp(p.o)) +
      '<div class="ad-tip__total">' + row("", L.lTotal + " · " + p.n + " " + L.lOrders, rp(p.t)) + "</div>";
    tip.hidden = false;
    var scale = box.clientWidth / geo.W, cx = geo.x(i) * scale, gap = geo.slot * scale / 2 + 8;
    var w = tip.offsetWidth;
    tip.style.left = (cx + gap + w <= box.clientWidth ? cx + gap : Math.max(0, cx - gap - w)) + "px";
    tip.style.top = "0px";
    geo.cross.setAttribute("x1", geo.x(i));
    geo.cross.setAttribute("x2", geo.x(i));
    geo.cross.classList.add("is-on");
  }
  function hide() {
    tip.hidden = true;
    active = -1;
    if (geo) geo.cross.classList.remove("is-on");
  }

  draw();
  var last = box.clientWidth;
  window.addEventListener("resize", function () {
    if (box.clientWidth !== last) { last = box.clientWidth; draw(); }
  });

  // Tombol Grafik / Tabel.
  var table = card.querySelector(".ad-trend__table");
  var hint = card.querySelector(".ad-chart-hint");
  if (table) table.hidden = true;  // tanpa JS tabel tetap tampil sebagai pengganti grafik
  card.querySelectorAll(".ad-switch button").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var asTable = btn.dataset.view === "table";
      card.querySelectorAll(".ad-switch button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === btn)); });
      box.hidden = asTable;
      if (hint) hint.hidden = asTable;
      if (table) table.hidden = !asTable;
      if (!asTable) draw();
    });
  });
})();
