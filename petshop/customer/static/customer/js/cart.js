function formatRupiah(angka) { 
    return 'Rp ' + parseInt(angka).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); 
}

function renderCart() {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    let tbody = document.getElementById('cart-items');
    let emptyMsg = document.getElementById('empty-cart');
    tbody.innerHTML = '';

    if (cart.length === 0) {
        emptyMsg.style.display = 'block';
        document.querySelector('.cart-table').style.display = 'none';
        document.querySelector('.summary-card').style.display = 'none';
    } else {
        emptyMsg.style.display = 'none';
        document.querySelector('.cart-table').style.display = 'table';
        document.querySelector('.summary-card').style.display = 'block';
        
        cart.forEach((item, index) => {
            tbody.innerHTML += `
                <tr>
                    <td>
                        <div class="d-flex align-items-center gap-3">
                            <div class="cart-item-photo">
                                ${item.photo ? `<img src="${item.photo}" alt="photo">` : '<span>Photo</span>'}
                            </div>
                            <span class="fw-semibold">${item.name}</span>
                        </div>
                    </td>
                    <td>${formatRupiah(item.price)}</td>
                    <td>
                        <div class="quantity-control">
                            <button class="qty-minus" data-index="${index}">-</button>
                            <span>${item.quantity}</span>
                            <button class="qty-plus" data-index="${index}">+</button>
                        </div>
                    </td>
                    <td class="fw-bold">${formatRupiah(item.price * item.quantity)}</td>
                    <td><button class="btn-delete" data-index="${index}"><i class="fas fa-trash"></i></button></td>
                </tr>
            `;
        });

        // Tambahkan event listener setelah elemen dibuat
        document.querySelectorAll('.qty-minus').forEach(btn => {
            btn.addEventListener('click', function() { updateQty(this.dataset.index, -1); });
        });
        document.querySelectorAll('.qty-plus').forEach(btn => {
            btn.addEventListener('click', function() { updateQty(this.dataset.index, 1); });
        });
        document.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', function() { deleteItem(this.dataset.index); });
        });
    }
    updateSummary();
    updateCartCount();
}

function updateQty(index, change) {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    cart[index].quantity += change;
    if (cart[index].quantity <= 0) cart.splice(index, 1);
    localStorage.setItem('petshop_cart', JSON.stringify(cart));
    renderCart();
}

function deleteItem(index) {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    cart.splice(index, 1);
    localStorage.setItem('petshop_cart', JSON.stringify(cart));
    renderCart();
}

function updateSummary() {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    let subtotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    document.getElementById('subtotal').textContent = formatRupiah(subtotal);
    document.getElementById('total').textContent = formatRupiah(subtotal + (cart.length > 0 ? 10000 : 0));
}

function updateCartCount() {
    let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
    let total = cart.reduce((sum, item) => sum + item.quantity, 0);
    let badge = document.getElementById('cart-count');
    if (badge) badge.textContent = total;
}

document.addEventListener('DOMContentLoaded', function() {
    renderCart();

    // Tangani tombol checkout dengan membaca data attribute dari HTML
    const checkoutBtn = document.getElementById('btn-checkout');
    if (checkoutBtn) {
        checkoutBtn.addEventListener('click', function() {
            let cart = JSON.parse(localStorage.getItem('petshop_cart')) || [];
            if (cart.length === 0) { 
                alert('Your cart is still empty!'); 
                return; 
            }
            window.location.href = this.getAttribute('data-checkout-url');
        });
    }
});