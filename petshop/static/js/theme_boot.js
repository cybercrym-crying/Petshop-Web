/* Mode terang/gelap halaman toko (pelanggan, landing, login) dan menu samping
   pelanggan yang diciutkan. Dimuat di <head> tanpa defer supaya tidak berkedip. */
(function () {
  "use strict";

  var root = document.documentElement;
  var THEME_KEY = "seellyTheme";
  var SIDE_KEY = "caNavCollapsed";
  var scheme = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function read(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function write(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      return;
    }
  }

  function saved() {
    var value = read(THEME_KEY);
    return value === "dark" || value === "light" ? value : null;
  }

  function sync() {
    var dark = root.getAttribute("data-theme") === "dark";
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      var label = dark ? buttons[i].getAttribute("data-label-light") : buttons[i].getAttribute("data-label-dark");
      buttons[i].setAttribute("aria-pressed", dark ? "true" : "false");
      if (label) {
        buttons[i].setAttribute("aria-label", label);
        buttons[i].setAttribute("title", label);
      }
    }
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-bs-theme", theme); // komponen Bootstrap ikut gelap
    sync();
  }

  apply(saved() || (scheme && scheme.matches ? "dark" : "light"));
  if (read(SIDE_KEY) === "1") root.classList.add("ca-collapsed");

  if (scheme) {
    var follow = function (event) {
      if (!saved()) apply(event.matches ? "dark" : "light");
    };
    if (scheme.addEventListener) scheme.addEventListener("change", follow);
    else if (scheme.addListener) scheme.addListener(follow);
  }

  document.addEventListener("DOMContentLoaded", sync);
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-theme-toggle]");
    if (!button) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    write(THEME_KEY, next);
    apply(next);
  });

  window.SiteTheme = { sideKey: SIDE_KEY, write: write };
})();
