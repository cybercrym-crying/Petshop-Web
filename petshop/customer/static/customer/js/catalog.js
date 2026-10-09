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
    
    alert('✅ ' + name + ' added to cart!');
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

// Jalankan saat halaman selesai dimuat
document.addEventListener('DOMContentLoaded', updateCartCount);