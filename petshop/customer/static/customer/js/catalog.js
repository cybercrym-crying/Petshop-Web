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
    showToast('✅ ' + name + ' ditambahkan ke keranjang');
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

    // Pencarian: ada dua kotak (desktop dan menu HP) yang disinkronkan. Di halaman Shop produk
    // disaring langsung di browser; di halaman lain form mengirim ?q= ke halaman Shop.
    const inputs = document.querySelectorAll('.js-search');
    const forms = document.querySelectorAll('.js-search-form');
    const mainSearch = document.getElementById('product-search');
    const onShop = !!document.getElementById('product-grid');
    function setQuery(value) {
        inputs.forEach(function (i) { i.value = value; });
    }
    if (onShop) {
        const q = new URLSearchParams(window.location.search).get('q');
        if (q) {
            setQuery(q);
            filterProducts();
        }
        inputs.forEach(function (input) {
            input.addEventListener('input', function () {
                setQuery(input.value);
                filterProducts();
            });
        });
        forms.forEach(function (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                filterProducts();
                closeMenu();
                const grid = document.getElementById('produk');
                if (grid) grid.scrollIntoView({ behavior: 'smooth' });
            });
        });
    }

    // Menu HP
    const toggle = document.getElementById('nav-toggle');
    const menu = document.getElementById('mobile-menu');
    function closeMenu() {
        if (!toggle || !menu) return;
        menu.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-label', 'Buka menu');
        const icon = toggle.querySelector('i');
        if (icon) icon.className = 'fas fa-bars';
    }
    if (toggle && menu) {
        toggle.addEventListener('click', function () {
            const open = menu.classList.toggle('is-open');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.setAttribute('aria-label', open ? 'Tutup menu' : 'Buka menu');
            const icon = toggle.querySelector('i');
            if (icon) icon.className = open ? 'fas fa-times' : 'fas fa-bars';
        });
        menu.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', closeMenu); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
    }
});
