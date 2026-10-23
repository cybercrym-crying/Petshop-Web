/*
 * Halaman keranjang: isi dari localStorage (window.Store), harga & stok
 * disamakan dulu dengan database lewat Store.refreshCart().
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  var root = document.querySelector("[data-cart-page]");
  if (!root || !window.Store) return;
  var Store = window.Store;

  var list = root.querySelector("[data-cart-items]");
  var empty = root.querySelector("[data-cart-empty]");
  var filled = root.querySelector("[data-cart-filled]");
  var loading = root.querySelector("[data-cart-loading]");
  var notice = root.querySelector("[data-cart-notice]");

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function photoOf(item) {
    var box = el("div", "cart-item__photo");
    var src = Store.safeUrl(item.photo);
    if (src) {
      var img = el("img");
      img.src = src;
      img.alt = "";
      img.loading = "lazy";
      img.addEventListener("error", function () {
        box.textContent = "";
        box.appendChild(el("i", "fas fa-paw"));
      });
      box.appendChild(img);
    } else {
      box.appendChild(el("i", "fas fa-paw"));
    }
    return box;
  }

  function qtyButton(label, symbol, disabled, onClick) {
    var button = el("button", "", symbol);
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.disabled = disabled;
    button.addEventListener("click", onClick);
    return button;
  }

  function row(item) {
    var li = el("li", "cart-item");
    li.appendChild(photoOf(item));

    var info = el("div", "cart-item__info");
    var url = Store.safeUrl(item.url);
    var name = url ? el("a", "cart-item__name", item.name) : el("span", "cart-item__name", item.name);
    if (url) name.href = url;
    info.appendChild(name);
    info.appendChild(el("span", "cart-item__price", Store.formatRupiah(item.price) + " / barang"));
    var stock = Store.stockOf(item);
    if (stock !== Infinity && stock <= 10) {
      info.appendChild(el("span", "cart-item__stock", tr("Sisa stok {n}", { n: stock })));
    }
    li.appendChild(info);

    var qty = el("div", "qty-control");
    qty.setAttribute("aria-label", "Jumlah " + item.name);
    qty.appendChild(qtyButton(tr("Kurangi jumlah"), "−", item.quantity <= 1, function () {
      Store.setQuantity(item.id, item.quantity - 1);
      render();
    }));
    qty.appendChild(el("span", "", String(item.quantity)));
    qty.appendChild(qtyButton(tr("Tambah jumlah"), "+", item.quantity >= stock, function () {
      Store.setQuantity(item.id, item.quantity + 1);
      render();
    }));
    li.appendChild(qty);

    li.appendChild(el("strong", "cart-item__subtotal", Store.formatRupiah(item.price * item.quantity)));

    var remove = el("button", "cart-item__remove");
    remove.type = "button";
    remove.setAttribute("aria-label", tr("Hapus {name} dari keranjang", { name: item.name }));
    remove.appendChild(el("i", "fas fa-trash-can"));
    remove.addEventListener("click", function () {
      Store.removeItem(item.id);
      Store.showToast(item.name + " dihapus dari keranjang");
      render();
    });
    li.appendChild(remove);
    return li;
  }

  function render() {
    var cart = Store.getCart();
    list.textContent = "";
    cart.forEach(function (item) { list.appendChild(row(item)); });
    empty.hidden = cart.length > 0;
    filled.hidden = cart.length === 0;
    root.querySelector("[data-cart-count]").textContent = Store.cartCount();
    root.querySelector("[data-cart-subtotal]").textContent = Store.formatRupiah(Store.cartTotal());
    root.querySelector("[data-cart-total]").textContent = Store.formatRupiah(Store.cartTotal());
  }

  function showNotice(lines, tone) {
    notice.textContent = "";
    lines.forEach(function (line) { notice.appendChild(el("p", "", line)); });
    notice.className = "cart-notice cart-notice--" + tone;
    notice.hidden = lines.length === 0;
  }

  Store.refreshCart(function (result) {
    loading.hidden = true;
    if (!result.ok) {
      showNotice([tr("Tidak bisa memeriksa harga terbaru (koneksi bermasalah). Harga akan dicek ulang saat checkout.")], "warn");
    } else if (result.changes.length) {
      showNotice(result.changes, "info");
    }
    render();
  });
  window.addEventListener("storage", render);
})();
