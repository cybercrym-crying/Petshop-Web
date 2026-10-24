/* Menu kurir: di layar lebar tombol ☰ menciutkan menu samping jadi deretan ikon
   (pilihan diingat); di HP membuka laci menu (juga tombol "Menu" di bawah). */
(function () {
  "use strict";

  var KEY = "courierNavCollapsed";
  var root = document.documentElement;
  var side = document.getElementById("ck-side");
  var buttons = document.querySelectorAll("[data-ck-menu]");
  var scrim = document.querySelector("[data-ck-close]");
  var topButton = document.querySelector(".ck-menu-btn");
  if (!side || !buttons.length) return;
  var desktop = window.matchMedia("(min-width: 992px)");

  function save(value) {
    try {
      window.localStorage.setItem(KEY, value);
    } catch (error) {
      // localStorage tidak tersedia: pilihan hanya berlaku di halaman ini.
    }
  }

  function syncDesktop() {
    var collapsed = desktop.matches && root.classList.contains("ck-collapsed");
    side.querySelectorAll(".ck-link").forEach(function (link) {
      var label = link.textContent.trim();
      if (collapsed) link.setAttribute("title", label);
      else link.removeAttribute("title");
    });
    if (!topButton) return;
    var open = desktop.matches ? !collapsed : document.body.classList.contains("ck-menu-open");
    topButton.setAttribute("aria-expanded", open ? "true" : "false");
    topButton.setAttribute("aria-label", topButton.getAttribute(open ? "data-label-close" : "data-label-open"));
  }

  function setOpen(open) {
    document.body.classList.toggle("ck-menu-open", open);
    if (scrim) scrim.hidden = !open;
    buttons.forEach(function (b) {
      b.setAttribute("aria-expanded", open ? "true" : "false");
    });
    syncDesktop();
    if (open) {
      var first = side.querySelector("a, button");
      if (first) first.focus();
    }
  }

  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      if (desktop.matches) {
        var collapsed = !root.classList.contains("ck-collapsed");
        root.classList.toggle("ck-collapsed", collapsed);
        save(collapsed ? "1" : "0");
        syncDesktop();
        return;
      }
      setOpen(!document.body.classList.contains("ck-menu-open"));
    });
  });
  if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && document.body.classList.contains("ck-menu-open")) {
      setOpen(false);
      buttons[0].focus();
    }
  });
  var onChange = function () {
    if (desktop.matches) setOpen(false);
    syncDesktop();
  };
  if (desktop.addEventListener) desktop.addEventListener("change", onChange);
  else if (desktop.addListener) desktop.addListener(onChange);
  syncDesktop();
})();
