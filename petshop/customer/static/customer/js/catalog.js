// Fungsi menambahkan produk ke keranjang (localStorage)
function addToCart(id, name, price, photo) {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    let existingItem = cart.find(item => item.id === id);

    if (existingItem) {
        existingItem.quantity += 1;
    } else {
        cart.push({
            id: id,
            name: name,
            price: price,
            photo: photo,
            quantity: 1
        });
    }

    localStorage.setItem('petshop_cart', JSON.stringify(cart));
    updateCartCount();
    showToast('✅ ' + name + ' added to cart');
}

// Fungsi memperbarui angka di ikon keranjang navbar
function updateCartCount() {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    let totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    let badge = document.getElementById('cart-count');
    if (badge) {
        badge.textContent = totalItems;
    }
}

// Notifikasi singkat (pengganti alert)
let toastTimer = null;
function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2000);
}

// Pencarian produk (sisi browser)
function filterProducts() {
    const input = document.getElementById('product-search');
    const query = input ? input.value.trim().toLowerCase() : '';
    const cols = document.querySelectorAll('.product-col');
    let visible = 0;
    cols.forEach(col => {
        const match = col.dataset.name.includes(query);
        col.classList.toggle('d-none', !match);
        if (match) visible += 1;
    });
    const empty = document.getElementById('no-results');
    if (empty) empty.classList.toggle('d-none', visible > 0 || cols.length === 0);
}

document.addEventListener('DOMContentLoaded', function () {
    updateCartCount();

    // Tombol Add to Cart membaca data-* (aman untuk nama berisi tanda kutip, dan produk tanpa foto)
    document.addEventListener('click', function (event) {
        const btn = event.target.closest('.btn-add-cart');
        if (!btn || btn.disabled) return;
        addToCart(
            parseInt(btn.dataset.id, 10),
            btn.dataset.name,
            parseInt(btn.dataset.price, 10) || 0,
            btn.dataset.photo || ''
        );
    });

    const search = document.getElementById('product-search');
    if (search) {
        search.addEventListener('input', filterProducts);
        search.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                filterProducts();
                const grid = document.getElementById('produk');
                if (grid) grid.scrollIntoView({ behavior: 'smooth' });
            }
        });
    }
    const searchBtn = document.getElementById('search-btn');
    if (searchBtn) searchBtn.addEventListener('click', filterProducts);
});
