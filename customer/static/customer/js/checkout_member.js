/*
 * Checkout untuk customer yang sudah login: keranjang (localStorage) dikirim ke
 * server sebagai pesanan. Server menghitung ulang harga & stok, lalu pesanan
 * masuk ke admin dengan status "Menunggu Konfirmasi".
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-member-checkout]");
  if (!root || !window.Store) return;
  var Store = window.Store;

  var itemsEl = root.querySelector("[data-co-items]");
  var emptyEl = root.querySelector("[data-co-empty]");
  var totalRow = root.querySelector("[data-co-total-row]");
  var totalEl = root.querySelector("[data-co-total]");
  var submitBtn = root.querySelector("[data-co-submit]");
  var errorEl = root.querySelector("[data-co-error]");
  var addressEl = document.getElementById("co-address");
  var noteEl = document.getElementById("co-note");
  var dialog = document.querySelector("[data-co-dialog]");
  var confirmBtn = dialog.querySelector("[data-co-confirm]");

  function paymentInput() {
    return root.querySelector('input[name="payment_method"]:checked');
  }

  function paymentLabel() {
    var input = paymentInput();
    var strong = input && input.closest("label").querySelector("strong");
    return strong ? strong.textContent : "";
  }

  function itemRow(item) {
    var li = document.createElement("li");
    li.className = "co-item";
    var info = document.createElement("div");
    var name = document.createElement("div");
    name.className = "co-item__name";
    name.textContent = item.name;
    var detail = document.createElement("div");
    detail.className = "co-item__detail";
    detail.textContent = item.quantity + " × " + Store.formatRupiah(item.price);
    info.appendChild(name);
    info.appendChild(detail);
    var price = document.createElement("div");
    price.className = "co-item__price";
    price.textContent = Store.formatRupiah(item.price * item.quantity);
    li.appendChild(info);
    li.appendChild(price);
    return li;
  }

  function render() {
    var cart = Store.getCart();
    itemsEl.textContent = "";
    cart.forEach(function (item) {
      itemsEl.appendChild(itemRow(item));
    });
    var empty = cart.length === 0;
    emptyEl.hidden = !empty;
    itemsEl.hidden = empty;
    totalRow.hidden = empty;
    submitBtn.hidden = empty;
    totalEl.textContent = Store.formatRupiah(Store.cartTotal());
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = !message;
    if (message) errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function openDialog() {
    showError("");
    var cart = Store.getCart();
    if (!cart.length) return;
    if (!addressEl.value.trim()) {
      addressEl.setCustomValidity("Alamat pengiriman wajib diisi.");
      addressEl.reportValidity();
      return;
    }
    var list = dialog.querySelector("[data-co-dialog-items]");
    list.textContent = "";
    cart.forEach(function (item) {
      list.appendChild(itemRow(item));
    });
    dialog.querySelector("[data-co-dialog-total]").textContent = Store.formatRupiah(Store.cartTotal());
    dialog.querySelector("[data-co-dialog-address]").textContent = addressEl.value.trim();
    dialog.querySelector("[data-co-dialog-payment]").textContent = paymentLabel();
    confirmBtn.disabled = false;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else if (window.confirm("Buat pesanan sekarang?")) send();
  }

  function send() {
    confirmBtn.disabled = true;
    var payment = paymentInput();
    var body = {
      items: Store.getCart().map(function (item) {
        return { id: item.id, quantity: item.quantity };
      }),
      payment_method: payment ? payment.value : "",
      address: addressEl.value.trim(),
      note: noteEl.value.trim(),
    };
    fetch(root.getAttribute("data-place-url"), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": root.getAttribute("data-csrf"),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body),
    })
      .then(function (response) {
        var type = response.headers.get("Content-Type") || "";
        if (type.indexOf("application/json") === -1) {
          throw new Error("Sesi login Anda berakhir. Muat ulang halaman lalu masuk kembali.");
        }
        return response.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.message || "Pesanan gagal dibuat.");
        Store.clearCart();
        window.location.href = data.redirect;
      })
      .catch(function (error) {
        if (dialog.open) dialog.close();
        showError(error.message || "Koneksi bermasalah, coba lagi.");
        confirmBtn.disabled = false;
      });
  }

  submitBtn.addEventListener("click", openDialog);
  confirmBtn.addEventListener("click", send);
  dialog.querySelector("[data-co-cancel]").addEventListener("click", function () {
    dialog.close();
  });
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });
  addressEl.addEventListener("input", function () {
    addressEl.setCustomValidity("");
  });
  window.addEventListener("storage", render);
  render();
})();
