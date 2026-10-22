/* Sidebar admin: buka/tutup (desktop mengingat pilihan terakhir; HP mulai tertutup) dan mode terang/gelap. */
(function () {
  var root = document.documentElement;
  var KEY = "staffNavCollapsed";
  var desktop = window.matchMedia("(min-width: 992px)");

  // --- Mode gelap: pilihan tersimpan, kalau belum ada ikuti pengaturan sistem ---
  var THEME_KEY = "staffTheme";
  var scheme = window.matchMedia("(prefers-color-scheme: dark)");

  function savedTheme() {
    try {
      var v = localStorage.getItem(THEME_KEY);
      return v === "dark" || v === "light" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    root.setAttribute("data-bs-theme", t); // supaya komponen Bootstrap ikut gelap
  }

  function syncTheme() {
    var dark = root.getAttribute("data-theme") === "dark";
    var btns = document.querySelectorAll("[data-staff-theme-toggle]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute("aria-pressed", dark ? "true" : "false");
      btns[i].setAttribute("aria-label", dark ? "Aktifkan mode terang" : "Aktifkan mode gelap");
    }
  }

  applyTheme(savedTheme() || (scheme.matches ? "dark" : "light"));

  // Jalan sebelum konten digambar supaya tidak berkedip.
  try {
    if (localStorage.getItem(KEY) === "1") root.classList.add("staff-collapsed");
  } catch (e) {}

  function isOpen() {
    return desktop.matches
      ? !root.classList.contains("staff-collapsed")
      : root.classList.contains("staff-open");
  }

  function sync() {
    var open = isOpen();
    var buttons = document.querySelectorAll("[data-staff-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute("aria-expanded", open ? "true" : "false");
    }
  }

  function setOpen(open) {
    if (desktop.matches) {
      root.classList.toggle("staff-collapsed", !open);
      try {
        localStorage.setItem(KEY, open ? "0" : "1");
      } catch (e) {}
    } else {
      root.classList.toggle("staff-open", open);
    }
    sync();
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-staff-theme-toggle]")) {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (err) {}
      syncTheme();
    } else if (e.target.closest("[data-staff-toggle]")) {
      setOpen(!isOpen());
    } else if (e.target.closest("[data-staff-backdrop]")) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !desktop.matches && isOpen()) setOpen(false);
  });

  desktop.addEventListener("change", function () {
    root.classList.remove("staff-open");
    sync();
  });

  scheme.addEventListener("change", function () {
    if (!savedTheme()) {
      applyTheme(scheme.matches ? "dark" : "light");
      syncTheme();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    sync();
    syncTheme();
  });
})();
