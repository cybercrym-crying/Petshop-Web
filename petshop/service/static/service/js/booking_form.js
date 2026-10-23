/*
 * Form booking layanan: sembunyikan isian nama/jenis bila memilih hewan tersimpan,
 * dan tampilkan peta jemput/antar hanya bila salah satu opsi antar-jemput dicentang.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-booking-form]");
  if (!form) return;
  var pet = form.querySelector("[name=pet]");
  var newPet = form.querySelector("[data-new-pet]");
  var detail = form.querySelector("[data-transport-detail]");
  var toggles = form.querySelectorAll("[name=pickup], [name=return_trip]");

  function syncPet() {
    if (!pet || pet.type === "hidden" || !newPet) return;
    newPet.hidden = !!pet.value;
  }

  function syncTransport() {
    var on = Array.prototype.some.call(toggles, function (t) { return t.checked; });
    var wasHidden = detail.hidden;
    detail.hidden = !on;
    // Leaflet perlu menghitung ulang ukuran peta yang baru tampil.
    if (on && wasHidden) window.dispatchEvent(new Event("resize"));
  }

  if (pet) pet.addEventListener("change", syncPet);
  Array.prototype.forEach.call(toggles, function (t) { t.addEventListener("change", syncTransport); });
  syncPet();
  syncTransport();
})();
