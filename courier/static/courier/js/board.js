(function () {
  "use strict";

  var board = document.querySelector("[data-board]");
  if (!board) {
    return;
  }

  var tabs = document.querySelectorAll("[data-board-tab]");
  var columns = board.querySelectorAll("[data-board-col]");

  function show(name) {
    for (var i = 0; i < tabs.length; i++) {
      var active = tabs[i].getAttribute("data-board-tab") === name;
      tabs[i].classList.toggle("is-active", active);
      tabs[i].setAttribute("aria-selected", active ? "true" : "false");
    }
    for (var j = 0; j < columns.length; j++) {
      columns[j].classList.toggle(
        "is-active",
        columns[j].getAttribute("data-board-col") === name
      );
    }
  }

  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-board-tab]");
    if (tab) {
      show(tab.getAttribute("data-board-tab"));
      return;
    }
    var link = event.target.closest("[data-board-link]");
    if (link) {
      show(link.getAttribute("data-board-link"));
    }
  });

  var hash = window.location.hash.replace("#col-", "");
  if (hash === "pending" || hash === "on_delivery" || hash === "done") {
    show(hash);
  } else {
    show("pending");
  }
})();
