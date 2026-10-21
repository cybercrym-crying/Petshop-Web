/*
 * Shared storefront logic: cart, wishlist, header badges, toast and the
 * "Added to Cart" modal. Cart and wishlist live in the browser (localStorage).
 */
(function () {
  "use strict";

  var CART_KEY = "petshop_cart";
  var WISHLIST_KEY = "petshop_wishlist";

  /* ---------- helpers ---------- */

  function readList(key) {
    try {
      var value = JSON.parse(localStorage.getItem(key));
      return Array.isArray(value) ? value : [];
    } catch (error) {
      return [];
    }
  }

  function writeList(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      /* storage may be blocked (private mode); the page still works for this visit */
    }
  }

  function formatRupiah(amount) {
    return "Rp " + Math.round(Number(amount) || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  /* Only allow same-site paths and http(s) links coming from storage. */
  function safeUrl(url) {
    url = String(url || "");
    return /^(\/(?!\/)|https?:\/\/)/.test(url) ? url : "";
  }

  function stockOf(item) {
    var stock = parseInt(item.stock, 10);
    return isNaN(stock) ? Infinity : stock;
  }

  /* ---------- cart ---------- */

  function getCart() {
    return readList(CART_KEY).filter(function (item) {
      return item && item.id != null && item.quantity > 0;
    });
  }

  function saveCart(cart) {
    writeList(CART_KEY, cart);
    updateBadges();
  }

  function cartCount() {
    return getCart().reduce(function (sum, item) { return sum + item.quantity; }, 0);
  }

  function cartTotal() {
    return getCart().reduce(function (sum, item) { return sum + item.price * item.quantity; }, 0);
  }

  function findItem(cart, id) {
    for (var i = 0; i < cart.length; i++) {
      if (String(cart[i].id) === String(id)) return cart[i];
    }
    return null;
  }

  /* Adds `quantity` of a product. Returns the cart item, or null if it cannot be added. */
  function addToCart(product, quantity) {
    var stock = stockOf(product);
    if (stock <= 0) return null;

    var cart = getCart();
    var item = findItem(cart, product.id);
    if (!item) {
      item = {
        id: product.id,
        name: product.name,
        price: product.price,
        photo: product.photo || "",
        url: product.url || "",
        stock: product.stock,
        quantity: 0
      };
      cart.push(item);
    }
    item.stock = product.stock;
    item.price = product.price;

    var wanted = item.quantity + (quantity || 1);
    if (wanted > stock) {
      wanted = stock;
      showToast("Stok " + product.name + " hanya tersisa " + stock);
    }
    item.quantity = wanted;
    saveCart(cart);
    return item;
  }

  function setQuantity(id, quantity) {
    var cart = getCart();
    var item = findItem(cart, id);
    if (!item) return null;
    item.quantity = Math.max(1, Math.min(quantity, stockOf(item)));
    saveCart(cart);
    return item;
  }

  function removeItem(id) {
    saveCart(getCart().filter(function (item) { return String(item.id) !== String(id); }));
  }

  function clearCart() {
    saveCart([]);
  }

  /* ---------- wishlist ---------- */

  function getWishlist() {
    return readList(WISHLIST_KEY).map(String);
  }

  function isWishlisted(id) {
    return getWishlist().indexOf(String(id)) !== -1;
  }

  function toggleWishlist(id) {
    var list = getWishlist();
    var index = list.indexOf(String(id));
    if (index === -1) list.push(String(id));
    else list.splice(index, 1);
    writeList(WISHLIST_KEY, list);
    updateBadges();
    document.dispatchEvent(new CustomEvent("wishlist:change"));
    return index === -1;
  }

  function syncWishlistButtons() {
    document.querySelectorAll("[data-wishlist-toggle]").forEach(function (button) {
      var active = isWishlisted(button.dataset.id);
      var icon = button.querySelector("i");
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      if (icon) icon.className = (active ? "fas" : "far") + " fa-heart";
    });
  }

  /* ---------- badges (only visible when there is something to show) ---------- */

  function setBadge(element, count) {
    if (!element) return;
    element.textContent = count > 99 ? "99+" : String(count);
    element.hidden = count <= 0;
  }

  function updateBadges() {
    setBadge(document.getElementById("cart-count"), cartCount());
    setBadge(document.getElementById("wishlist-count"), getWishlist().length);
  }

  /* ---------- toast ---------- */

  var toastTimer = null;

  function showToast(message) {
    var toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 2200);
  }

  /* ---------- "Added to Cart" modal ---------- */

  var modal = null;
  var modalItemId = null;
  var lastFocus = null;

  function renderModal() {
    var item = findItem(getCart(), modalItemId);
    if (!item) return;
    var photo = safeUrl(item.photo);

    document.getElementById("modal-name").textContent = item.name;
    document.getElementById("modal-price").textContent = formatRupiah(item.price) + " each";
    document.getElementById("modal-qty").textContent = item.quantity;
    document.getElementById("modal-items").textContent = cartCount();
    document.getElementById("modal-total").textContent = formatRupiah(cartTotal());
    document.getElementById("modal-photo").innerHTML = photo
      ? '<img src="' + escapeHtml(photo) + '" alt="">'
      : '<i class="fas fa-paw" aria-hidden="true"></i>';
    document.getElementById("modal-minus").disabled = item.quantity <= 1;
    document.getElementById("modal-plus").disabled = item.quantity >= stockOf(item);
  }

  function openCartModal(item) {
    if (!modal) return;
    modalItemId = item.id;
    renderModal();
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    var viewCart = modal.querySelector(".btn-primary-seelly");
    if (viewCart) viewCart.focus();
  }

  function closeCartModal() {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function trapFocus(event) {
    if (event.key !== "Tab") return;
    var focusable = modal.querySelectorAll("a[href], button:not([disabled])");
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function setupModal() {
    modal = document.getElementById("cart-modal");
    if (!modal) return;

    modal.addEventListener("click", function (event) {
      if (event.target === modal || event.target.closest("[data-modal-close]")) closeCartModal();
    });
    modal.addEventListener("keydown", trapFocus);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeCartModal();
    });
    document.getElementById("modal-minus").addEventListener("click", function () {
      var item = findItem(getCart(), modalItemId);
      if (item) setQuantity(modalItemId, item.quantity - 1);
      renderModal();
    });
    document.getElementById("modal-plus").addEventListener("click", function () {
      var item = findItem(getCart(), modalItemId);
      if (item) setQuantity(modalItemId, item.quantity + 1);
      renderModal();
    });
  }

  /* ---------- page wiring ---------- */

  function readProduct(button) {
    return {
      id: parseInt(button.dataset.id, 10),
      name: button.dataset.name,
      price: parseInt(button.dataset.price, 10) || 0,
      stock: parseInt(button.dataset.stock, 10),
      photo: button.dataset.photo || "",
      url: button.dataset.url || ""
    };
  }

  function setupNav() {
    var toggle = document.getElementById("nav-toggle");
    var links = document.getElementById("nav-links");
    if (!toggle || !links) return;
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  document.addEventListener("click", function (event) {
    var addButton = event.target.closest("[data-add-to-cart]");
    if (addButton && !addButton.disabled) {
      var quantity = 1;
      if (addButton.hasAttribute("data-use-detail-qty")) {
        quantity = parseInt(document.getElementById("detail-qty").textContent, 10) || 1;
      }
      var item = addToCart(readProduct(addButton), quantity);
      if (item) openCartModal(item);
      return;
    }

    var heart = event.target.closest("[data-wishlist-toggle]");
    if (heart) {
      var added = toggleWishlist(heart.dataset.id);
      syncWishlistButtons();
      showToast(added ? "Ditambahkan ke favorit" : "Dihapus dari favorit");
    }
  });

  window.addEventListener("storage", function () {
    updateBadges();
    syncWishlistButtons();
  });

  document.addEventListener("DOMContentLoaded", function () {
    setupNav();
    setupModal();
    updateBadges();
    syncWishlistButtons();
  });

  window.Store = {
    formatRupiah: formatRupiah,
    escapeHtml: escapeHtml,
    safeUrl: safeUrl,
    stockOf: stockOf,
    getCart: getCart,
    cartCount: cartCount,
    cartTotal: cartTotal,
    setQuantity: setQuantity,
    removeItem: removeItem,
    clearCart: clearCart,
    getWishlist: getWishlist,
    showToast: showToast
  };
})();
