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

function placeOrder(event) {
  if (event) event.preventDefault();

  let cart = JSON.parse(localStorage.getItem("petshop_cart")) || [];

  if (cart.length === 0) {
    alert("Keranjang belanja Anda kosong!");
    return;
  }

  // Get form data
  let form = document.getElementById("checkout-form");
  let formData = new FormData(form);

  let nama = formData.get("nama");
  let no_wa = formData.get("no_wa");
  let alamat = formData.get("alamat");
  let payment_method = document.querySelector(
    'input[name="payment_method"]:checked',
  ).value;

  // Validate form
  if (!nama || !no_wa || !alamat) {
    alert(
      "Mohon isi semua kolom wajib (Nama, Nomor Telepon, dan Alamat)!",
    );
    return;
  }

  // Build WhatsApp message
  let nomor_admin = "6281356703075";

  let pesan = `Halo Kak, mau order barang dong\n\n`;
  pesan += `*Format Pemesanan*\n`;
  pesan += `• Nama Lengkap: ${nama}\n`;
  pesan += `• No. HP/WA: ${no_wa}\n`;
  pesan += `• Alamat Lengkap: ${alamat}\n`;
  pesan += `• Metode Pembayaran: ${payment_method}\n\n`;
  pesan += `*Ringkasan Pesanan:*\n`;

  let total = 0;
  cart.forEach((item) => {
    let subtotal = item.price * item.quantity;
    total += subtotal;
    pesan += `- ${item.name} - ${item.quantity}x (${formatRupiah(item.price)}) = ${formatRupiah(subtotal)}\n`;
  });

  pesan += `\n*Total Estimasi: ${formatRupiah(total)}*\n`;
  pesan += `\nMohon info total biaya + ongkirnya ya kak. Terima kasih!`;

  // Redirect to WhatsApp
  let url = `https://wa.me/${nomor_admin}?text=${encodeURIComponent(pesan)}`;
  window.open(url, "_blank");

  localStorage.removeItem("petshop_cart");
  renderOrderSummary();
}

// Render on page load
document.addEventListener("DOMContentLoaded", renderOrderSummary);

