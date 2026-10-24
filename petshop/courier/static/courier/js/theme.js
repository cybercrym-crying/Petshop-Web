(function () {
  "use strict";

  var STORAGE_KEY = "courier-theme";
  var root = document.documentElement;

  function readStored() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (error) {
      return null;
    }
  }

  function writeStored(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch (error) {
      return;
    }
  }

  function preferred() {
    var stored = readStored();
    if (stored) {
      return stored;
    }
    var prefersDark =
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  }

  function apply(theme) {
    root.setAttribute("data-bs-theme", theme);
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      var dark = theme === "dark";
      var icon = buttons[i].querySelector("i");
      buttons[i].setAttribute("aria-pressed", dark ? "true" : "false");
      buttons[i].setAttribute(
        "aria-label",
        dark ? "Beralih ke mode terang" : "Beralih ke mode gelap"
      );
      buttons[i].setAttribute("title", dark ? "Mode terang" : "Mode gelap");
      if (icon) {
        icon.className = dark ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
      }
    }
  }

  apply(preferred());

  // Menu samping yang diciutkan (layar lebar) dipasang sebelum halaman digambar.
  try {
    if (window.localStorage.getItem("courierNavCollapsed") === "1") root.classList.add("ck-collapsed");
  } catch (error) {
    // localStorage tidak tersedia: menu tetap terbuka.
  }

  document.addEventListener("DOMContentLoaded", function () {
    apply(root.getAttribute("data-bs-theme") || preferred());
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-theme-toggle]");
    if (!button) {
      return;
    }
    var next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    writeStored(next);
    apply(next);
  });
})();
