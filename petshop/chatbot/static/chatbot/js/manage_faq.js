/* Buka modal "Tambah FAQ" otomatis saat datang dari tombol "Jadikan FAQ". */
document.addEventListener("DOMContentLoaded", function () {
  var modal = document.querySelector("[data-autoshow]");
  if (modal && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modal).show();
});
