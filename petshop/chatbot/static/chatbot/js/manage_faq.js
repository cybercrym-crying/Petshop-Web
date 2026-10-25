/* Kelola FAQ chatbot: buka modal otomatis, saring & cari daftar, sisipkan [[layanan]] / [[wa]]. */
document.addEventListener("DOMContentLoaded", function () {
  // Buka modal "Tambah FAQ" otomatis saat datang dari tombol "Jadikan FAQ".
  var modal = document.querySelector("[data-autoshow]");
  if (modal && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modal).show();

  // Saring (Semua / Pilihan cepat / Nonaktif) + cari teks.
  var nav = document.querySelector("[data-fq-filter]");
  var search = document.querySelector("[data-fq-search]");
  var items = document.querySelectorAll(".fq-item");
  var none = document.querySelector(".fq-none");
  var mode = "all";
  function apply() {
    var q = search ? search.value.trim().toLowerCase() : "";
    var shown = 0;
    items.forEach(function (it) {
      var ok = mode === "all" || (mode === "quick" && it.dataset.quick) || (mode === "off" && it.dataset.off);
      if (ok && q) ok = it.dataset.text.indexOf(q) !== -1;
      it.hidden = !ok;
      if (ok) shown++;
    });
    if (none) none.hidden = shown > 0;
  }
  if (nav) {
    nav.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-show]");
      if (!btn) return;
      nav.querySelectorAll("button").forEach(function (b) {
        var on = b === btn;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      mode = btn.dataset.show;
      apply();
    });
  }
  if (search) search.addEventListener("input", apply);

  // Sisipkan penanda ke jawaban pada posisi kursor.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-insert]");
    if (!btn) return;
    var area = btn.closest("form").querySelector("[data-fq-answer]");
    if (!area) return;
    var text = btn.dataset.insert;
    var start = area.selectionStart, end = area.selectionEnd;
    area.value = area.value.slice(0, start) + text + area.value.slice(end);
    area.focus();
    area.setSelectionRange(start + text.length, start + text.length);
  });
});
