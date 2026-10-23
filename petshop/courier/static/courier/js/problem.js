/* Pilihan kendala umum mengisi kolom catatan. */
(function () {
  "use strict";
  var preset = document.querySelector("[data-problem-preset]");
  var note = document.getElementById("problem-note");
  if (!preset || !note) return;
  preset.addEventListener("change", function () {
    if (preset.value) note.value = preset.value;
  });
})();
