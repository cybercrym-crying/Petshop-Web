(function () {
  "use strict";

  var dialog = document.getElementById("order-modal");

  if (!dialog) {
    return;
  }

  function navigateToDetail(card) {
    var detailUrl = card && card.dataset && card.dataset.detailUrl;
    if (!detailUrl) {
      return;
    }
    window.location.href = detailUrl;
  }

  document.addEventListener("click", function (event) {
    var card = event.target.closest("[data-order-id]");
    if (card) {
      navigateToDetail(card);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    var card = event.target.closest("[data-order-id]");
    if (card && card === event.target) {
      event.preventDefault();
      navigateToDetail(card);
    }
  });

  dialog.querySelector('[data-action="cancel"]').addEventListener("click", function () {
    dialog.close();
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      dialog.close();
    }
  });
})();
