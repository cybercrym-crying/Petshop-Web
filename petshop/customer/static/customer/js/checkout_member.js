/*
 * Checkout untuk customer yang sudah login: keranjang (localStorage) dikirim ke
 * server sebagai pesanan. Server menghitung ulang harga & stok, lalu pesanan
 * masuk ke admin dengan status "Menunggu Konfirmasi".
 * Titik peta (store/js/map_picker.js) wajib; ongkir diminta ke server setiap titik berubah.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

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
  var latEl = document.getElementById("co-lat");
  var lngEl = document.getElementById("co-lng");
  var mapEl = root.querySelector("[data-map-picker]");
  var shipEl = root.querySelector("[data-co-ship]");
  var distanceEl = root.querySelector("[data-co-distance]");
  var shipInfo = root.querySelector("[data-co-ship-info]");
  var quote = null; // {fee, distance_km} dari server, null = belum ada titik / di luar jangkauan
  var quoteSeq = 0;

  function grandTotal() {
    return Store.cartTotal() + (quote ? quote.fee : 0);
  }

  function renderShipping(message, bad) {
    if (quote) {
      shipEl.textContent = Store.formatRupiah(quote.fee);
      distanceEl.textContent = "(" + quote.distance_km.toFixed(1) + " km)";
    } else {
      shipEl.textContent = message || tr("Pilih titik di peta");
      distanceEl.textContent = "";
    }
    shipEl.classList.toggle("co-ship-bad", !!bad);
    totalEl.textContent = Store.formatRupiah(grandTotal());
  }

  function fetchQuote() {
    if (!latEl.value || !lngEl.value) return;
    mapEl.classList.remove("is-missing");
    var seq = ++quoteSeq;
    quote = null;
    renderShipping("Menghitung…");
    var url = root.getAttribute("data-quote-url") + "?latitude=" + encodeURIComponent(latEl.value) + "&longitude=" + encodeURIComponent(lngEl.value);
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (seq !== quoteSeq) return;
        if (data.ok) {
          quote = { fee: data.fee, distance_km: data.distance_km };
          renderShipping();
          shipInfo.textContent = tr("Titik tersimpan. Jarak dari toko ±{km} km.", { km: data.distance_km.toFixed(1) });
        } else {
          renderShipping(tr("Di luar jangkauan"), true);
          shipInfo.textContent = data.message;
        }
      })
      .catch(function () {
        if (seq === quoteSeq) renderShipping(tr("Gagal menghitung ongkir"), true);
      });
  }
  latEl.addEventListener("change", fetchQuote);

  /* Satu token per percobaan checkout: kirim ulang (klik dobel, koneksi putus
   * lalu dicoba lagi) tidak membuat pesanan kedua di server. */
  var clientToken = newToken();

  function newToken() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 12);
  }

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
    totalEl.textContent = Store.formatRupiah(grandTotal());
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
      addressEl.setCustomValidity(tr("Alamat pengiriman wajib diisi."));
      addressEl.reportValidity();
      return;
    }
    if (!quote) {
      mapEl.classList.add("is-missing");
      mapEl.scrollIntoView({ behavior: "smooth", block: "center" });
      showError(latEl.value ? tr("Titik pengiriman di luar jangkauan antar toko.") : tr("Tandai titik lokasi pengiriman di peta dulu."));
      return;
    }
    var list = dialog.querySelector("[data-co-dialog-items]");
    list.textContent = "";
    cart.forEach(function (item) {
      list.appendChild(itemRow(item));
    });
    dialog.querySelector("[data-co-dialog-ship]").textContent = Store.formatRupiah(quote.fee) + " (" + quote.distance_km.toFixed(1) + " km)";
    dialog.querySelector("[data-co-dialog-total]").textContent = Store.formatRupiah(grandTotal());
    dialog.querySelector("[data-co-dialog-address]").textContent = addressEl.value.trim();
    dialog.querySelector("[data-co-dialog-payment]").textContent = paymentLabel();
    confirmBtn.disabled = false;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else if (window.confirm(tr("Buat pesanan sekarang?"))) send();
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
      expected_total: grandTotal(),
      latitude: latEl.value,
      longitude: lngEl.value,
      client_token: clientToken,
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
        if (response.status >= 500) {
          throw new Error(tr("Server sedang bermasalah. Coba lagi beberapa saat lagi."));
        }
        var type = response.headers.get("Content-Type") || "";
        if (type.indexOf("application/json") === -1) {
          throw new Error(tr("Sesi login Anda berakhir. Muat ulang halaman lalu masuk kembali."));
        }
        return response.json();
      })
      .then(function (data) {
        if (data.reason === "price_changed") {
          // Harga berubah: segarkan keranjang, tampilkan total baru, minta konfirmasi ulang.
          clientToken = newToken();
          Store.refreshCart(function () { render(); });
          fetchQuote();
          throw new Error(data.message);
        }
        if (!data.ok) throw new Error(data.message || tr("Pesanan gagal dibuat."));
        Store.clearCart();
        window.location.href = data.redirect;
      })
      .catch(function (error) {
        if (dialog.open) dialog.close();
        showError(error.message || tr("Koneksi bermasalah, coba lagi."));
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
  submitBtn.disabled = true;
  render();
  fetchQuote();
  Store.refreshCart(function (result) {
    render();
    submitBtn.disabled = false;
    if (result.changes.length) showError(result.changes.join(" "));
  });
})();
