// Akun kurir: tombol "Ganti foto" membuka pemilih file, lalu pratinjau foto
// yang dipilih tampil di avatar sebelum disimpan.
(function () {
    document.querySelectorAll("[data-photo-pick]").forEach(function (input) {
        var box = document.querySelector(input.dataset.photoPick);
        var name = document.querySelector("[data-photo-name]");
        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (!file) return;
            if (name) name.textContent = file.name;
            if (!box) return;
            var img = document.createElement("img");
            img.className = "ck-avatar ck-avatar--lg";
            img.alt = "";
            img.src = URL.createObjectURL(file);
            box.replaceChildren(img);
        });
    });
})();
