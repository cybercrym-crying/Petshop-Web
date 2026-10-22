(function () {
  "use strict";

  var page = document.getElementById("wishlist-page");
  if (!page) return;

  var grid = document.getElementById("wishlist-grid");
  var loading = document.getElementById("wishlist-loading");
  var empty = document.getElementById("wishlist-empty");
  var failed = document.getElementById("wishlist-error");
  var sub = document.getElementById("wishlist-sub");
  var retry = document.getElementById("wishlist-retry");
  var itemsUrl = page.getAttribute("data-items-url");

  function show(state) {
    grid.hidden = state !== "grid";
    loading.hidden = state !== "loading";
    empty.hidden = state !== "empty";
    failed.hidden = state !== "error";
  }

  function countCards() {
    return grid.querySelectorAll(".product-card").length;
  }

  function updateSub() {
    var total = countCards();
    sub.textContent = total > 0 ? total + " produk favorit" : "";
  }

  function load() {
    var saved = window.Store.getWishlist();
    if (saved.length === 0) {
      grid.textContent = "";
      updateSub();
      show("empty");
      return;
    }

    show("loading");
    var ids = saved.slice().reverse().join(",");

    fetch(itemsUrl + "?ids=" + encodeURIComponent(ids), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      })
      .then(function (html) {
        grid.innerHTML = html;
        window.Store.syncWishlistButtons();

        var found = [];
        grid.querySelectorAll(".product-card").forEach(function (card) {
          found.push(card.dataset.productId);
        });
        if (found.length !== saved.length) {
          window.Store.setWishlist(
            saved.filter(function (id) {
              return found.indexOf(id) !== -1;
            })
          );
        }

        updateSub();
        show(countCards() > 0 ? "grid" : "empty");
      })
      .catch(function () {
        show("error");
      });
  }

  function onChange() {
    var saved = window.Store.getWishlist();
    grid.querySelectorAll(".product-card").forEach(function (card) {
      if (saved.indexOf(card.dataset.productId) !== -1) return;
      card.classList.add("is-leaving");
      window.setTimeout(function () {
        card.remove();
        updateSub();
        if (countCards() === 0) show("empty");
      }, 200);
    });
  }

  retry.addEventListener("click", load);
  document.addEventListener("wishlist:change", onChange);
  window.addEventListener("storage", load);
  document.addEventListener("DOMContentLoaded", load);
})();
