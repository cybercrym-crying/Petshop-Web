// Booking Layanan: memilih tanggal di kalender langsung membuka hari itu.
(function () {
    var form = document.querySelector("[data-bk-day]");
    if (!form) return;
    var input = form.querySelector('input[type="date"]');
    input.addEventListener("change", function () {
        if (input.value) form.submit();
    });
    form.querySelector("label").addEventListener("click", function (e) {
        if (typeof input.showPicker === "function") {
            e.preventDefault();
            try { input.showPicker(); } catch (err) { input.focus(); }
        }
    });
})();
