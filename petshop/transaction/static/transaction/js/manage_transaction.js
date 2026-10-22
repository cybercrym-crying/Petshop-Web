document.querySelectorAll(".order-card[data-modal]").forEach(function (card) {
    card.addEventListener("click", function (e) {
        if (e.target.closest("a, button, form, input, select, textarea, label")) return;
        var modal = document.querySelector(card.dataset.modal);
        if (modal && window.bootstrap) bootstrap.Modal.getOrCreateInstance(modal).show();
    });
});

// Trigger animasi ulang saat tab diganti (Optional, agar setiap pindah tab kartunya muncul lagi)
var tabEls = document.querySelectorAll('button[data-bs-toggle="pill"]');
tabEls.forEach(function(tabEl) {
    tabEl.addEventListener('shown.bs.tab', function (event) {
        var targetId = event.target.getAttribute("data-bs-target");
        var cards = document.querySelectorAll(targetId + ' .animate-fade-up');

        cards.forEach(function(card) {
            card.style.animation = 'none';
            card.offsetHeight; /* Trigger reflow */
            card.style.animation = null;
        });
    });
});
