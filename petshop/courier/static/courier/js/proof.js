(function () {
  "use strict";

  // Pratinjau foto sebelum dikirim, supaya kurir yakin fotonya benar.
  var inputs = document.querySelectorAll("[data-proof-form] input[type=file]");
  for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("change", function (event) {
      var input = event.target;
      var img = input.closest("form").querySelector(".proof-preview");
      var file = input.files && input.files[0];
      if (!file) {
        img.hidden = true;
        return;
      }
      img.src = URL.createObjectURL(file);
      img.hidden = false;
    });
  }
})();
