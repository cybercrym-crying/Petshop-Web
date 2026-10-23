/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function formatRupiah(angka) {
  return (
    "Rp " +
    parseInt(angka)
      .toString()
      .replace(/\B(?=(\d{3})+(?!\d))/g, ".")
  );
}

function renderOrderSummary() {
  let cart = getCart();
  let orderItemsContainer = document.getElementById("order-items");
  let emptyCart = document.getElementById("empty-cart");

  orderItemsContainer.innerHTML = "";

  // Keranjang kosong: form pengiriman & pembayaran tidak perlu diisi, sembunyikan.
  document.querySelectorAll(".delivery-section, .payment-section").forEach(function (el) {
    el.hidden = cart.length === 0;
  });

  if (cart.length === 0) {
    emptyCart.hidden = false;
    document.querySelector(".total-section").hidden = true;
    document.querySelector(".btn-place-order").hidden = true;
  } else {
    emptyCart.hidden = true;
    document.querySelector(".total-section").hidden = false;
    document.querySelector(".btn-place-order").hidden = false;

    let total = 0;

    cart.forEach((item, index) => {
      let subtotal = item.price * item.quantity;
      total += subtotal;

      orderItemsContainer.innerHTML += `
                <div class="order-item">
                    <div>
                        <div class="item-name">${escapeHtml(item.name)}</div>
                        <div class="item-details">${item.quantity} x ${formatRupiah(item.price)}</div>
                    </div>
                    <div class="item-price">${formatRupiah(subtotal)}</div>
                </div>
            `;
    });

    document.getElementById("total-price").textContent = formatRupiah(total);
  }
}

/* Nomor admin diambil dari halaman (satu sumber: Pengaturan Toko). */
var WHATSAPP_ADMIN = (document.querySelector("[data-wa-number]") || { dataset: {} }).dataset.waNumber || "";

function getCart() {
  return window.Store ? window.Store.getCart() : [];
}

function clearCart() {
  if (window.Store) window.Store.clearCart();
}

function cartTotal(cart) {
  return cart.reduce(function (sum, item) {
    return sum + item.price * item.quantity;
  }, 0);
}

function readCheckoutData() {
  var form = document.getElementById("checkout-form");
  var data = new FormData(form);
  var payment = document.querySelector('input[name="payment_method"]:checked');
  return {
    name: String(data.get("nama") || "").trim(),
    phone: String(data.get("no_wa") || "").trim(),
    address: String(data.get("alamat") || "").trim(),
    payment: payment ? payment.value : "",
  };
}

function phoneError(value) {
  var digits = value.replace(/[\s\-().]/g, "");
  if (!digits) return tr("Nomor telepon wajib diisi.");
  if (!/^(\+?62|0)\d{8,13}$/.test(digits)) {
    return tr("Nomor telepon tidak valid. Contoh: 081234567890");
  }
  return "";
}

function requiredError(label) {
  return function (value) {
    return value.trim() ? "" : tr("{label} wajib diisi.", { label: tr(label) });
  };
}

function validateCheckoutForm() {
  var form = document.getElementById("checkout-form");
  var rules = [
    ["nama", requiredError("Nama lengkap")],
    ["no_wa", phoneError],
    ["alamat", requiredError("Alamat")],
  ];
  rules.forEach(function (rule) {
    var input = form.elements[rule[0]];
    input.setCustomValidity(rule[1](input.value));
  });
  return form.reportValidity();
}

function buildWhatsappUrl(data, cart) {
  var pesan = "Halo Kak, mau order barang dong\n\n";
  pesan += "*Format Pemesanan*\n";
  pesan += "• Nama Lengkap: " + data.name + "\n";
  pesan += "• No. HP/WA: " + data.phone + "\n";
  pesan += "• Alamat Lengkap: " + data.address + "\n";
  pesan += "• Metode Pembayaran: " + data.payment + "\n\n";
  pesan += "*Ringkasan Pesanan:*\n";

  cart.forEach(function (item) {
    var subtotal = item.price * item.quantity;
    pesan +=
      "- " + item.name + " - " + item.quantity + "x (" + formatRupiah(item.price) + ") = " + formatRupiah(subtotal) + "\n";
  });

  pesan += "\n*Total Estimasi: " + formatRupiah(cartTotal(cart)) + "*\n";
  pesan += "\nMohon info total biaya + ongkirnya ya kak. Terima kasih!";

  return "https://wa.me/" + WHATSAPP_ADMIN + "?text=" + encodeURIComponent(pesan);
}

function buildPlainSummary(data, cart) {
  var lines = [tr("Periksa pesanan Anda:"), ""];
  lines.push(tr("Nama") + ": " + data.name, tr("Telepon") + ": " + data.phone, tr("Alamat") + ": " + data.address, tr("Pembayaran") + ": " + data.payment, "");
  cart.forEach(function (item) {
    lines.push(item.quantity + " x " + item.name + " = " + formatRupiah(item.price * item.quantity));
  });
  lines.push("", "Total: " + formatRupiah(cartTotal(cart)), "", tr("Kirim pesanan sekarang?"));
  return lines.join("\n");
}

function fillConfirmDialog(data, cart) {
  document.getElementById("confirm-name").textContent = data.name;
  document.getElementById("confirm-phone").textContent = data.phone;
  document.getElementById("confirm-address").textContent = data.address;
  document.getElementById("confirm-payment").textContent = data.payment;
  document.getElementById("confirm-total").textContent = formatRupiah(cartTotal(cart));

  var list = document.getElementById("confirm-items");
  list.textContent = "";
  cart.forEach(function (item) {
    var row = document.createElement("li");
    row.className = "confirm-item";

    var info = document.createElement("div");
    var name = document.createElement("div");
    name.className = "confirm-item__name";
    name.textContent = item.name;
    var detail = document.createElement("div");
    detail.className = "confirm-item__detail";
    detail.textContent = item.quantity + " x " + formatRupiah(item.price);
    info.appendChild(name);
    info.appendChild(detail);

    var price = document.createElement("div");
    price.className = "confirm-item__price";
    price.textContent = formatRupiah(item.price * item.quantity);

    row.appendChild(info);
    row.appendChild(price);
    list.appendChild(row);
  });

  var check = document.getElementById("confirm-check");
  check.checked = false;
  document.querySelector("[data-confirm-send]").disabled = true;
}

function sendOrder() {
  var cart = getCart();
  var dialog = document.getElementById("confirm-dialog");

  if (cart.length === 0) {
    dialog.close();
    alert(tr("Keranjang belanja Anda kosong!"));
    renderOrderSummary();
    return;
  }

  var sendButton = document.querySelector("[data-confirm-send]");
  sendButton.disabled = true;

  window.open(buildWhatsappUrl(readCheckoutData(), cart), "_blank");

  clearCart();
  dialog.close();
  renderOrderSummary();
}

function placeOrder(event) {
  if (event) event.preventDefault();

  var cart = getCart();
  if (cart.length === 0) {
    alert(tr("Keranjang belanja Anda kosong!"));
    return;
  }

  if (!validateCheckoutForm()) return;

  var data = readCheckoutData();
  var dialog = document.getElementById("confirm-dialog");

  if (typeof dialog.showModal !== "function") {
    if (window.confirm(buildPlainSummary(data, cart))) {
      window.open(buildWhatsappUrl(data, cart), "_blank");
      clearCart();
      renderOrderSummary();
    }
    return;
  }

  fillConfirmDialog(data, cart);
  dialog.showModal();
}

document.addEventListener("DOMContentLoaded", function () {
  renderOrderSummary();
  if (window.Store) window.Store.refreshCart(renderOrderSummary);
});

document.addEventListener("input", function (event) {
  if (event.target.closest("#checkout-form") && event.target.setCustomValidity) {
    event.target.setCustomValidity("");
  }
  if (event.target.id === "confirm-check") {
    document.querySelector("[data-confirm-send]").disabled = !event.target.checked;
  }
});

document.addEventListener("click", function (event) {
  if (event.target.closest("[data-place-order]")) {
    placeOrder(event);
    return;
  }
  if (event.target.closest("[data-confirm-back]")) {
    document.getElementById("confirm-dialog").close();
    return;
  }
  if (event.target.closest("[data-confirm-send]")) {
    if (document.getElementById("confirm-check").checked) sendOrder();
    return;
  }
  if (event.target.id === "confirm-dialog") {
    event.target.close();
  }
});
