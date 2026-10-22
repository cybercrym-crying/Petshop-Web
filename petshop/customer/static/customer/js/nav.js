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

  function setupSearchToggle() {
    var toggle = document.getElementById("nav-search-toggle");
    var form = document.getElementById("nav-search");
    if (!toggle || !form) return;
    toggle.addEventListener("click", function () {
      var open = !form.classList.contains("open");
      form.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        var input = form.querySelector("input");
        if (input) input.focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (!form.classList.contains("open")) return;
      if (form.contains(event.target) || toggle.contains(event.target)) return;
      form.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    });
  }

  function setupAccountMenu() {
    var root = document.querySelector("[data-account]");
    if (!root) return;
    var button = root.querySelector("button[aria-haspopup]");
    var menu = root.querySelector(".sn-menu");

    function setOpen(open) {
      menu.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
    }

    button.addEventListener("click", function () {
      setOpen(menu.hidden);
    });
    document.addEventListener("click", function (event) {
      if (!root.contains(event.target)) setOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !menu.hidden) {
        setOpen(false);
        button.focus();
      }
    });
  }

  window.addEventListener("storage", refreshBadges);
  document.addEventListener("wishlist:change", refreshBadges);

  document.addEventListener("DOMContentLoaded", function () {
    setupMenu();
    setupSearchToggle();
    setupAccountMenu();
    refreshBadges();
  });

  window.SiteNav = { refreshBadges: refreshBadges };
})();
