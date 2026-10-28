/* Halaman login & daftar: tampilkan / sembunyikan kata sandi.
   Tombol: data-toggle-password="<id input>" (kosong = #password). */
document.addEventListener("click", function (event) {
  const btn = event.target.closest("[data-toggle-password]");
  if (!btn) return;
  const input = document.getElementById(btn.getAttribute("data-toggle-password") || "password");
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  const iconShow = btn.querySelector("[data-icon-show]") || document.getElementById("icon-show");
  const iconHide = btn.querySelector("[data-icon-hide]") || document.getElementById("icon-hide");
  if (iconShow) iconShow.classList.toggle("d-none", show);
  if (iconHide) iconHide.classList.toggle("d-none", !show);
  const label = show ? btn.dataset.labelHide : btn.dataset.labelShow;
  if (label) btn.setAttribute("aria-label", label);
});
