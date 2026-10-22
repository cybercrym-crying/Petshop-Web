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
  let cart = JSON.parse(localStorage.getItem("petshop_cart")) || [];
  let orderItemsContainer = document.getElementById("order-items");
  let emptyCart = document.getElementById("empty-cart");

  orderItemsContainer.innerHTML = "";

  if (cart.length === 0) {
    emptyCart.style.display = "block";
    document.querySelector(".total-section").style.display = "none";
    document.querySelector(".btn-place-order").style.display = "none";
  } else {
    emptyCart.style.display = "none";
    document.querySelector(".total-section").style.display = "block";
    document.querySelector(".btn-place-order").style.display = "flex";

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

var WHATSAPP_ADMIN = "6281356703075";

function getCart() {
  return JSON.parse(localStorage.getItem("petshop_cart")) || [];
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
  if (!digits) return "Nomor telepon wajib diisi.";
  if (!/^(\+?62|0)\d{8,13}$/.test(digits)) {
    return "Nomor telepon tidak valid. Contoh: 081234567890";
  }
  return "";
}

function requiredError(label) {
  return function (value) {
    return value.trim() ? "" : label + " wajib diisi.";
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
  var lines = ["Periksa pesanan Anda:", ""];
  lines.push("Nama: " + data.name, "Telepon: " + data.phone, "Alamat: " + data.address, "Pembayaran: " + data.payment, "");
  cart.forEach(function (item) {
    lines.push(item.quantity + " x " + item.name + " = " + formatRupiah(item.price * item.quantity));
  });
  lines.push("", "Total: " + formatRupiah(cartTotal(cart)), "", "Kirim pesanan sekarang?");
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
    alert("Keranjang belanja Anda kosong!");
    renderOrderSummary();
    return;
  }

  var sendButton = document.querySelector("[data-confirm-send]");
  sendButton.disabled = true;

  window.open(buildWhatsappUrl(readCheckoutData(), cart), "_blank");

  localStorage.removeItem("petshop_cart");
  dialog.close();
  renderOrderSummary();
}

function placeOrder(event) {
  if (event) event.preventDefault();

  var cart = getCart();
  if (cart.length === 0) {
    alert("Keranjang belanja Anda kosong!");
    return;
  }

  if (!validateCheckoutForm()) return;

  var data = readCheckoutData();
  var dialog = document.getElementById("confirm-dialog");

  if (typeof dialog.showModal !== "function") {
    if (window.confirm(buildPlainSummary(data, cart))) {
      window.open(buildWhatsappUrl(data, cart), "_blank");
      localStorage.removeItem("petshop_cart");
      renderOrderSummary();
    }
    return;
  }

  fillConfirmDialog(data, cart);
  dialog.showModal();
}

document.addEventListener("DOMContentLoaded", renderOrderSummary);

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
