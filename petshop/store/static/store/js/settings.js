// Pengaturan Toko: sorot bagian aktif di navigasi, kalkulator ongkir, pratinjau QRIS/struk/WA,
// dan penanda "belum disimpan".
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";
  var form = document.querySelector("[data-st-form]");
  if (!form) return;
  function el(name) { return form.querySelector('[name="' + name + '"]'); }
  function num(name) { var f = el(name); return f ? parseFloat(String(f.value).replace(",", ".")) || 0 : 0; }
  function rp(n) { return "Rp " + Math.round(n).toLocaleString("id-ID"); }

  // Sama dengan tiered_fee di server: dasar untuk km pertama + per km berikutnya (dibulatkan ke atas).
  function fee(km, base, baseKm, perKm) { return base + Math.ceil(Math.max(0, km - baseKm)) * perKm; }
  var range = form.querySelector("[data-st-km]");
  function sim() {
    if (!range) return;
    var km = parseFloat(range.value);
    form.querySelector("[data-st-km-out]").textContent = km.toLocaleString("id-ID");
    var ship = form.querySelector("[data-st-ship]");
    var max = num("max_delivery_km");
    if (max && km > max) {
      ship.textContent = tr("Di luar jangkauan");
      ship.classList.add("is-bad");
    } else {
      ship.textContent = rp(fee(km, num("shipping_base_fee"), num("shipping_base_km"), num("shipping_per_km")));
      ship.classList.remove("is-bad");
    }
    var one = fee(km, num("pickup_base_fee"), num("pickup_base_km"), num("pickup_per_km"));
    form.querySelector("[data-st-pet1]").textContent = rp(one);
    form.querySelector("[data-st-pet2]").textContent = rp(one * 2);
  }
  if (range) range.addEventListener("input", sim);

  // Pratinjau nama toko & catatan kaki struk, dan tautan tes WhatsApp.
  function previews() {
    var footer = form.querySelector("[data-st-receipt-footer]");
    if (footer && el("receipt_footer")) footer.textContent = el("receipt_footer").value;
    var name = form.querySelector("[data-st-receipt-name]");
    if (name && el("name")) name.textContent = el("name").value;
    var wa = form.querySelector("[data-st-wa-test]");
    if (wa && el("whatsapp")) {
      var digits = el("whatsapp").value.replace(/\D/g, "");
      if (digits.charAt(0) === "0") digits = "62" + digits.slice(1);
      wa.href = "https://wa.me/" + digits;
    }
  }

  // QRIS: pratinjau gambar yang dipilih sebelum disimpan.
  var qris = form.querySelector("[data-st-qris-input]");
  if (qris) {
    qris.addEventListener("change", function () {
      var file = qris.files && qris.files[0];
      if (!file) return;
      var img = document.createElement("img");
      img.alt = "";
      img.src = URL.createObjectURL(file);
      form.querySelector("[data-st-qris-preview]").replaceChildren(img);
      form.querySelector("[data-st-qris-name]").textContent = file.name;
    });
  }

  // Penanda perubahan + peringatan saat meninggalkan halaman.
  var bar = form.querySelector("[data-st-bar]");
  var dirty = false;
  function markDirty(e) {
    if (e && e.target === range) return;
    previews();
    sim();
    if (dirty) return;
    dirty = true;
    bar.classList.add("is-dirty");
    form.querySelector("[data-st-state]").hidden = true;
    form.querySelector("[data-st-dirty]").hidden = false;
  }
  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);
  form.addEventListener("submit", function () { dirty = false; });
  window.addEventListener("beforeunload", function (e) {
    if (!dirty) return;
    e.preventDefault();
    e.returnValue = "";
  });

  // Navigasi bagian: sorot bagian yang sedang terlihat.
  var nav = document.querySelector("[data-st-nav]");
  if (nav && "IntersectionObserver" in window) {
    var links = {};
    nav.querySelectorAll("a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting || !links[entry.target.id]) return;
        nav.querySelectorAll("a").forEach(function (a) { a.classList.remove("is-on"); });
        links[entry.target.id].classList.add("is-on");
        if (nav.scrollWidth > nav.clientWidth) links[entry.target.id].scrollIntoView({ block: "nearest", inline: "center" });
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    form.querySelectorAll(".st-card[id]").forEach(function (s) { observer.observe(s); });
  }

  sim();
})();
