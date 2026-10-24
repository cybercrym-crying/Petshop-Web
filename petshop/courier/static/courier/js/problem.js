/* Pilihan kendala umum (chip) mengisi kolom catatan; kurir masih bisa menambah cerita. */
(function () {
  "use strict";
  var note = document.getElementById("problem-note");
  if (!note) return;
  document.querySelectorAll("[data-problem-preset]").forEach(function (preset) {
    preset.addEventListener("change", function () {
      if (preset.value) note.value = preset.value + ". ";
      note.focus();
    });
  });
})();
