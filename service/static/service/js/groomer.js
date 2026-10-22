/* Kartu booking groomer: klik/Enter membuka detail, tombol aksi minta konfirmasi bila perlu. */
(function () {
  "use strict";

  function open(card) {
    var url = card && card.getAttribute("data-booking-url");
    if (url) window.location.href = url;
  }

  document.addEventListener("click", function (e) {
    var confirmBtn = e.target.closest("[data-confirm]");
    if (confirmBtn && !window.confirm(confirmBtn.getAttribute("data-confirm"))) {
      e.preventDefault();
      return;
    }
    if (e.target.closest("form, button, a")) return;
    open(e.target.closest("[data-booking-url]"));
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var card = e.target.closest("[data-booking-url]");
    if (card && card === e.target) {
      e.preventDefault();
      open(card);
    }
  });
})();
