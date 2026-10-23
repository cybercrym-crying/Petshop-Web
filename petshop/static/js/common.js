/*
 * Perilaku kecil yang dipakai banyak halaman, dipicu lewat atribut data-* di HTML
 * (menggantikan atribut onclick / onsubmit / onchange langsung di template).
 *
 *   data-confirm="Pesan"      form / tombol: minta konfirmasi dulu sebelum dikirim
 *   data-href="/url"          elemen (mis. <tr>, <button>) yang berfungsi sebagai tautan saat diklik
 *   data-stop-propagation     klik pada elemen ini tidak diteruskan ke elemen induknya
 *   data-autosubmit           <select>/<input>: kirim form otomatis saat nilainya berubah
 */
(function () {
  "use strict";

  /* Hentikan bubbling klik (mis. tautan di dalam baris tabel yang bisa diklik). */
  document.querySelectorAll("[data-stop-propagation]").forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.stopPropagation();
    });
  });

  /* Konfirmasi pada tombol/tautan. */
  document.addEventListener("click", function (event) {
    var el = event.target.closest("[data-confirm]");
    if (!el || el.tagName === "FORM") return;
    if (!window.confirm(el.getAttribute("data-confirm"))) event.preventDefault();
  });

  /* Konfirmasi pada form. */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches || !form.matches("form[data-confirm]")) return;
    if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
  });

  /* Elemen yang berfungsi sebagai tautan. */
  document.addEventListener("click", function (event) {
    var el = event.target.closest("[data-href]");
    if (el) window.location.href = el.getAttribute("data-href");
  });

  /* Kirim form saat pilihan berubah. */
  document.addEventListener("change", function (event) {
    var el = event.target;
    if (el.matches && el.matches("[data-autosubmit]") && el.form) el.form.submit();
  });
})();

/* data-print: tombol cetak halaman (label paket, struk). */
document.addEventListener("click", function (event) {
  if (event.target.closest("[data-print]")) window.print();
});
