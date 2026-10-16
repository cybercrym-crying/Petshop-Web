/* Checkout page: shows the order summary and sends the order to WhatsApp. */
(function () {
  "use strict";

  var Store = window.Store;
  var form = document.getElementById("checkout-form");
  var alertBox = document.getElementById("form-alert");
  var submitButton = document.getElementById("btn-place-order");
  var submitLabel = submitButton.innerHTML;

  function renderSummary() {
    var cart = Store.getCart();
    var isEmpty = cart.length === 0;

    form.hidden = isEmpty;
    document.getElementById("checkout-empty").hidden = !isEmpty;

    document.getElementById("order-items").innerHTML = cart
      .map(function (item) {
        return (
          '<div class="order-item">' +
            "<div>" +
              '<div class="item-name">' + Store.escapeHtml(item.name) + "</div>" +
              '<div class="item-details">' + item.quantity + " × " + Store.formatRupiah(item.price) + "</div>" +
            "</div>" +
            '<div class="item-price">' + Store.formatRupiah(item.price * item.quantity) + "</div>" +
          "</div>"
        );
      })
      .join("");
    document.getElementById("total-price").textContent = Store.formatRupiah(Store.cartTotal());
  }

  function clearErrors() {
    form.querySelectorAll("[data-error-for]").forEach(function (element) { element.textContent = ""; });
    form.querySelectorAll(".invalid").forEach(function (element) { element.classList.remove("invalid"); });
    alertBox.hidden = true;
  }

  function showErrors(errors) {
    Object.keys(errors).forEach(function (field) {
      var target = form.querySelector('[data-error-for="' + field + '"]');
      var input = form.elements[field];
      if (target) target.textContent = errors[field];
      if (input && input.classList) input.classList.add("invalid");
    });
    if (errors.cart) {
      alertBox.textContent = errors.cart;
      alertBox.hidden = false;
    }
    var firstInvalid = form.querySelector(".invalid");
    if (firstInvalid) firstInvalid.focus();
  }

  function validateLocally() {
    var errors = {};
    if (!form.elements.name.value.trim()) errors.name = "Please enter your full name.";
    if (!/^\+?[\d\s().-]{9,20}$/.test(form.elements.phone.value.trim())) {
      errors.phone = "Please enter a valid phone number, e.g. 081234567890.";
    }
    if (!form.elements.address.value.trim()) errors.address = "Please enter your delivery address.";
    return errors;
  }

  function setBusy(busy) {
    submitButton.disabled = busy;
    submitButton.innerHTML = busy ? '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Sending…' : submitLabel;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearErrors();

    var errors = validateLocally();
    if (Object.keys(errors).length) {
      showErrors(errors);
      return;
    }

    var cart = Store.getCart();
    var data = new FormData(form);
    data.set(
      "cart_data",
      JSON.stringify(cart.map(function (item) { return { id: item.id, quantity: item.quantity }; }))
    );

    setBusy(true);
    fetch(form.action, {
      method: "POST",
      body: data,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (response) {
        return response.json().then(function (body) { return { ok: response.ok, body: body }; });
      })
      .then(function (result) {
        if (result.ok && result.body.ok) {
          Store.clearCart();
          Store.showToast("Opening WhatsApp…");
          window.location.href = result.body.whatsapp_url;
          return;
        }
        setBusy(false);
        showErrors(result.body.errors || { cart: "Something went wrong. Please try again." });
      })
      .catch(function () {
        setBusy(false);
        showErrors({ cart: "Could not reach the server. Please check your connection and try again." });
      });
  });

  window.addEventListener("pageshow", renderSummary);
  document.addEventListener("DOMContentLoaded", renderSummary);
})();
