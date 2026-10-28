// Akun Saya: pilih foto profil → pratinjau langsung, lalu otomatis diunggah.
(function () {
  var form = document.querySelector("[data-acc-photo]");
  if (!form) return;
  var input = form.querySelector("[data-acc-photo-input]");
  var box = form.querySelector("[data-acc-photo-preview]");
  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    var img = document.createElement("img");
    img.alt = "";
    img.src = URL.createObjectURL(file);
    box.replaceChildren(img);
    form.classList.add("is-busy");
    form.submit();
  });
})();
