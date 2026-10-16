/* Cart page: lists the items saved in the browser and lets the customer edit them. */
(function () {
  "use strict";

  var Store = window.Store;

  function itemHtml(item) {
    var photo = Store.safeUrl(item.photo);
    var url = Store.safeUrl(item.url);
    var name = Store.escapeHtml(item.name);
    var image = photo
      ? '<img src="' + Store.escapeHtml(photo) + '" alt="">'
      : '<i class="fas fa-paw" aria-hidden="true"></i>';
    var nameHtml = url
      ? '<a class="cart-name" href="' + Store.escapeHtml(url) + '">' + name + "</a>"
      : '<span class="cart-name">' + name + "</span>";
    var atLimit = item.quantity >= Store.stockOf(item);

    return (
      '<article class="cart-item" data-id="' + Store.escapeHtml(item.id) + '">' +
        '<div class="cart-photo">' + image + "</div>" +
        '<div class="cart-info">' + nameHtml +
          '<div class="cart-unit">' + Store.formatRupiah(item.price) + " each</div>" +
        "</div>" +
        '<div class="qty-control" aria-label="Quantity of ' + name + '">' +
          '<button type="button" data-action="minus" aria-label="Decrease quantity"' + (item.quantity <= 1 ? " disabled" : "") + ">−</button>" +
          "<span>" + item.quantity + "</span>" +
          '<button type="button" data-action="plus" aria-label="Increase quantity"' + (atLimit ? " disabled" : "") + ">+</button>" +
        "</div>" +
        '<div class="cart-subtotal">' + Store.formatRupiah(item.price * item.quantity) + "</div>" +
        '<button type="button" class="cart-remove" data-action="remove" aria-label="Remove ' + name + '">' +
          '<i class="fas fa-trash" aria-hidden="true"></i></button>' +
      "</article>"
    );
  }

  function render() {
    var cart = Store.getCart();
    var list = document.getElementById("cart-items");
    var empty = document.getElementById("empty-cart");
    var summary = document.getElementById("cart-summary-col");
    var isEmpty = cart.length === 0;

    list.innerHTML = cart.map(itemHtml).join("");
    list.hidden = isEmpty;
    empty.hidden = !isEmpty;
    summary.hidden = isEmpty;

    var total = Store.formatRupiah(Store.cartTotal());
    document.getElementById("summary-items").textContent = Store.cartCount();
    document.getElementById("subtotal").textContent = total;
    document.getElementById("total").textContent = total;
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-action]");
    var row = event.target.closest(".cart-item");
    if (!button || !row) return;

    var id = row.dataset.id;
    var item = Store.getCart().filter(function (entry) { return String(entry.id) === id; })[0];
    if (!item) return;

    if (button.dataset.action === "plus") Store.setQuantity(id, item.quantity + 1);
    if (button.dataset.action === "minus") Store.setQuantity(id, item.quantity - 1);
    if (button.dataset.action === "remove") {
      Store.removeItem(id);
      Store.showToast("Removed " + item.name);
    }
    render();
  });

  window.addEventListener("storage", render);
  document.addEventListener("DOMContentLoaded", render);
})();
