/* Form daftar staf: isian kendaraan hanya tampil bila memilih Kurir. */
(function () {
  "use strict";
  var form = document.querySelector("[data-staff-register]");
  if (!form) return;
  var select = form.querySelector("[data-role-select]");
  function sync() {
    var courier = select.value === "KURIR";
    form.querySelectorAll(".courier-only").forEach(function (el) {
      el.hidden = !courier;
    });
  }
  select.addEventListener("change", sync);
  sync();
})();
