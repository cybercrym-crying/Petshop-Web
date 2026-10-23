/* Struk: tombol Cetak, dan cetak otomatis tepat setelah transaksi dibayar (?print=1). */
(function () {
  "use strict";
  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });
  if (document.body.hasAttribute("data-auto-print")) {
    window.addEventListener("load", function () {
      window.setTimeout(function () { window.print(); }, 300);
      // Hapus ?print=1 supaya muat ulang halaman tidak mencetak lagi.
      if (window.history.replaceState) window.history.replaceState(null, "", window.location.pathname);
    });
  }
})();
