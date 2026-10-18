/* Halaman login: tampilkan / sembunyikan password. */
document.addEventListener("click", function (event) {
  const btn = event.target.closest("[data-toggle-password]");
  if (!btn) return;
  const input = document.getElementById("password");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  document.getElementById("icon-show").classList.toggle("d-none", show);
  document.getElementById("icon-hide").classList.toggle("d-none", !show);
  btn.setAttribute(
    "aria-label",
    show ? "Sembunyikan password" : "Tampilkan password",
  );
});
