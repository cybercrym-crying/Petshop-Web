(function () {
  "use strict";

  var CART_KEY = "petshop_cart";
  var WISHLIST_KEY = "petshop_wishlist";

  function readList(key) {
    try {
      var value = JSON.parse(localStorage.getItem(key));
      return Array.isArray(value) ? value : [];
    } catch (error) {
      return [];
    }
  }

  function setBadge(element, count) {
    if (!element) return;
    element.textContent = count > 99 ? "99+" : String(count);
    element.hidden = count <= 0;
  }

  function refreshBadges() {
    var cartItems = readList(CART_KEY).reduce(function (sum, item) {
      return sum + (parseInt(item.quantity, 10) || 0);
    }, 0);
    setBadge(document.getElementById("cart-count"), cartItems);
    setBadge(document.getElementById("wishlist-count"), readList(WISHLIST_KEY).length);
  }

  function setupMenu() {
    var toggle = document.getElementById("nav-toggle");
    var links = document.getElementById("nav-links");
    if (!toggle || !links) return;

    function setOpen(open) {
      links.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Tutup menu" : "Buka menu");
      var icon = toggle.querySelector("i");
      if (icon) icon.className = open ? "fas fa-times" : "fas fa-bars";
    }

    toggle.addEventListener("click", function () {
      setOpen(!links.classList.contains("open"));
    });
    links.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        setOpen(false);
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setOpen(false);
    });
  }

  window.addEventListener("storage", refreshBadges);
  document.addEventListener("wishlist:change", refreshBadges);

  document.addEventListener("DOMContentLoaded", function () {
    setupMenu();
    refreshBadges();
  });

  window.SiteNav = { refreshBadges: refreshBadges };
})();
