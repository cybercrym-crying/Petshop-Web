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

  // Area pelanggan: di layar lebar tombol bilah atas menciutkan menu samping jadi
  // deretan ikon (pilihan diingat); di HP membuka laci menu (juga tombol "Menu" di bawah).
  function setupAppMenu() {
    var side = document.getElementById("ca-side");
    var buttons = document.querySelectorAll("[data-ca-menu]");
    var scrim = document.querySelector("[data-ca-close]");
    if (!side || !buttons.length) return;
    var root = document.documentElement;
    var desktop = window.matchMedia("(min-width: 992px)");
    var topButton = document.querySelector(".ca-menu-btn");

    side.querySelectorAll(".ca-link").forEach(function (link) {
      var text = link.textContent.replace(/\s+\d+\s*$/, "").trim();
      if (text && !link.hasAttribute("title")) link.setAttribute("data-ca-tip", text);
    });

    function syncTips() {
      var collapsed = desktop.matches && root.classList.contains("ca-collapsed");
      side.querySelectorAll("[data-ca-tip]").forEach(function (link) {
        if (collapsed) link.setAttribute("title", link.getAttribute("data-ca-tip"));
        else link.removeAttribute("title");
      });
      if (topButton && desktop.matches) {
        topButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
        topButton.setAttribute("aria-label", topButton.getAttribute(collapsed ? "data-label-open" : "data-label-close"));
      }
    }

    function setCollapsed(collapsed) {
      root.classList.toggle("ca-collapsed", collapsed);
      if (window.SiteTheme) window.SiteTheme.write(window.SiteTheme.sideKey, collapsed ? "1" : "0");
      syncTips();
    }

    function setOpen(open) {
      document.body.classList.toggle("ca-menu-open", open);
      if (scrim) scrim.hidden = !open;
      buttons.forEach(function (b) {
        b.setAttribute("aria-expanded", open ? "true" : "false");
      });
      if (open) {
        var first = side.querySelector("a, button");
        if (first) first.focus();
      }
    }

    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        if (desktop.matches) {
          setCollapsed(!root.classList.contains("ca-collapsed"));
          return;
        }
        setOpen(!document.body.classList.contains("ca-menu-open"));
      });
    });
    if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && document.body.classList.contains("ca-menu-open")) {
        setOpen(false);
        buttons[0].focus();
      }
    });
    var onChange = function () {
      if (desktop.matches) setOpen(false);
      else if (topButton) {
        topButton.setAttribute("aria-expanded", "false");
        topButton.setAttribute("aria-label", topButton.getAttribute("data-label-open"));
      }
      syncTips();
    };
    if (desktop.addEventListener) desktop.addEventListener("change", onChange);
    else if (desktop.addListener) desktop.addListener(onChange);
    syncTips();
  }

  window.addEventListener("storage", refreshBadges);
  document.addEventListener("wishlist:change", refreshBadges);

  document.addEventListener("DOMContentLoaded", function () {
    setupMenu();
    setupSearchToggle();
    setupAccountMenu();
    setupAppMenu();
    refreshBadges();
  });

  window.SiteNav = { refreshBadges: refreshBadges };
})();
