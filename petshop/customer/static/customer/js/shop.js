/* Shop, home and product detail behaviour (filters, sorting, quantity, wishlist view). */
(function () {
  "use strict";

  function popular() {
      var track = document.getElementById("popular-track");
      if (!track) return;
      function step() { return track.clientWidth * 0.8; }
      document.getElementById("popular-prev").addEventListener("click", function () {
          track.scrollBy({ left: -step(), behavior: "smooth" });
      });
      document.getElementById("popular-next").addEventListener("click", function () {
          track.scrollBy({ left: step(), behavior: "smooth" });
      });
  };

  /* Sort select submits the filter form straight away. */
  function setupSort() {
    var select = document.getElementById("sort-select");
    var form = document.getElementById("filter-form");
    if (!select || !form) return;
    select.addEventListener("change", function () {
      if (form.requestSubmit) form.requestSubmit();
      else form.submit();
    });
  }

  /* Filters collapse behind a button on small screens. */
  function setupFilterToggle() {
    var button = document.getElementById("filter-toggle");
    var panel = document.getElementById("filter-panel");
    if (!button || !panel) return;
    button.addEventListener("click", function () {
      var open = panel.classList.toggle("open");
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* Quantity stepper on the product detail page. */
  function setupDetailQuantity() {
    var minus = document.getElementById("detail-minus");
    var plus = document.getElementById("detail-plus");
    var qty = document.getElementById("detail-qty");
    var add = document.getElementById("detail-add");
    if (!minus || !plus || !qty || !add) return;

    var stock = parseInt(add.dataset.stock, 10) || 0;

    function render(value) {
      qty.textContent = value;
      minus.disabled = value <= 1;
      plus.disabled = value >= stock;
    }

    minus.addEventListener("click", function () { render(Math.max(1, parseInt(qty.textContent, 10) - 1)); });
    plus.addEventListener("click", function () { render(Math.min(stock, parseInt(qty.textContent, 10) + 1)); });
    render(stock > 0 ? 1 : 0);
  }

  /* Wishlist view: the server lists every product, the browser keeps only saved ones. */
  function setupWishlistView() {
    var grid = document.getElementById("product-grid");
    if (!grid || !grid.hasAttribute("data-wishlist-mode")) return;

    function apply() {
      var saved = window.Store.getWishlist();
      var visible = 0;
      grid.querySelectorAll(".product-card").forEach(function (card) {
        var show = saved.indexOf(card.dataset.productId) !== -1;
        card.hidden = !show;
        if (show) visible += 1;
      });
      var empty = document.getElementById("wishlist-empty");
      if (empty) empty.hidden = visible > 0;
      grid.hidden = visible === 0;
      var sub = document.getElementById("shop-sub");
      if (sub && visible > 0) sub.textContent = visible + " saved product" + (visible === 1 ? "" : "s");
      else if (sub) sub.textContent = "";
    }

    document.addEventListener("wishlist:change", apply);
    apply();
  }

  document.addEventListener("DOMContentLoaded", function () {
    popular();
    setupSort();
    setupFilterToggle();
    setupDetailQuantity();
    setupWishlistView();
  });
})();
