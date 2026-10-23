/*
 * Perilaku tata letak bersama semua halaman (dimuat di setiap layout).
 *
 *   <table data-stack>   di layar sempit tiap baris tampil sebagai kartu; label kolom diambil
 *                        dari <thead>, jadi template tidak perlu menulis data-label satu per satu.
 *   body.is-typing       ditambahkan selama kolom isian aktif, dipakai untuk menyembunyikan
 *                        tombol melayang (chatbot) agar tidak menutupi kolom di HP.
 */
(function () {
  "use strict";

  document.querySelectorAll("table[data-stack]").forEach(function (table) {
    var heads = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) {
      return th.textContent.trim();
    });
    table.querySelectorAll("tbody tr").forEach(function (tr) {
      var col = 0;
      Array.prototype.forEach.call(tr.children, function (td) {
        if (!td.hasAttribute("data-label") && heads[col]) td.setAttribute("data-label", heads[col]);
        col += td.colSpan || 1;
      });
    });
  });

  /* Kartu yang berperan sebagai tombol (mis. membuka modal) juga bisa dibuka dengan Enter/Spasi. */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var el = e.target.closest('[role="button"][tabindex]');
    if (!el || el.tagName === "BUTTON" || el.tagName === "A") return;
    e.preventDefault();
    el.click();
  });

  var typing = function (on) { document.body.classList.toggle("is-typing", on); };
  document.addEventListener("focusin", function (e) {
    if (e.target.matches("input:not([type=checkbox]):not([type=radio]):not([type=submit]), textarea, select")) typing(true);
  });
  document.addEventListener("focusout", function () { typing(false); });
})();
