/* Struk (halaman staf): cetak otomatis tepat setelah transaksi dibayar (?print=1). Tombol Cetak ditangani common.js. */
(function () {
  "use strict";
  if (!document.querySelector("[data-auto-print]")) return;
  window.addEventListener("load", function () {
    window.setTimeout(function () { window.print(); }, 300);
    // Hapus ?print=1 supaya muat ulang halaman tidak mencetak lagi.
    if (window.history.replaceState) window.history.replaceState(null, "", window.location.pathname);
  });
})();
