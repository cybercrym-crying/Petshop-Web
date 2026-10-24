(function () {
  "use strict";

  var grid = document.querySelector(".groom-grid");
  var chips = document.querySelectorAll("[data-pet-filter]");
  if (!grid || !chips.length) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".groom-card"));

  function apply(filter) {
    var shown = 0;
    cards.forEach(function (card) {
      var pet = card.getAttribute("data-pet");
      var show = filter === "all" || pet === filter || pet === "semua-hewan";
      card.hidden = !show;
      card.classList.remove("is-wide");
      if (show) {
        shown += 1;
        if (shown % 3 === 0) card.classList.add("is-wide");
      }
    });
    Array.prototype.forEach.call(chips, function (chip) {
      var on = chip.getAttribute("data-pet-filter") === filter;
      chip.classList.toggle("is-on", on);
      chip.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  grid.setAttribute("data-js", "");
  Array.prototype.forEach.call(chips, function (chip) {
    chip.addEventListener("click", function () {
      apply(chip.getAttribute("data-pet-filter"));
    });
  });
  apply("all");
})();
