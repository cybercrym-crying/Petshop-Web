// Pelanggan baru dari kasir: simpan lewat fetch, lalu tambahkan & pilih di <select name="customer">.
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
    "use strict";
    var form = document.querySelector("[data-qc]");
    var modalEl = document.getElementById("quickCustomerModal");
    if (!form || !modalEl || !window.bootstrap) return;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    var errorBox = form.querySelector("[data-qc-error]");
    var save = form.querySelector("[data-qc-save]");
    var back = null; // modal asal yang dibuka lagi setelah selesai
    var target = null; // <select> yang memicu

    document.querySelectorAll("[data-qc-open]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            target = document.querySelector(btn.getAttribute("data-qc-target") || 'select[name="customer"]');
            var sel = btn.getAttribute("data-qc-return");
            back = sel ? document.querySelector(sel) : null;
            if (back) {
                // Isian modal asal tidak di-reset saat ditutup sementara.
                back.dataset.qcKeep = "1";
                back.addEventListener("hidden.bs.modal", function () { modal.show(); }, { once: true });
                bootstrap.Modal.getOrCreateInstance(back).hide();
            } else {
                modal.show();
            }
        });
    });
    modalEl.addEventListener("shown.bs.modal", function () {
        var name = form.querySelector('[name="name"]');
        if (name) name.focus();
    });
    modalEl.addEventListener("hidden.bs.modal", function () {
        if (back) {
            var b = back;
            back = null;
            bootstrap.Modal.getOrCreateInstance(b).show();
            window.setTimeout(function () { delete b.dataset.qcKeep; }, 400);
        }
    });

    function showErrors(errors) {
        form.querySelectorAll(".is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
        var lines = [];
        Object.keys(errors || {}).forEach(function (field) {
            var input = form.querySelector('[name="' + field + '"]');
            if (input && input.type !== "hidden") input.classList.add("is-invalid");
            lines = lines.concat(errors[field]);
        });
        errorBox.textContent = lines.join(" ") || tr("Gagal menyimpan. Coba lagi.");
        errorBox.hidden = false;
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        var missing = Array.prototype.filter.call(form.querySelectorAll("[required]"), function (el) {
            return !el.value.trim();
        });
        if (missing.length) {
            showErrors({});
            errorBox.textContent = tr("Isi nama, nomor WhatsApp, dan alamat.");
            missing.forEach(function (el) { el.classList.add("is-invalid"); });
            missing[0].focus();
            return;
        }
        save.disabled = true;
        fetch(form.action, {
            method: "POST",
            body: new FormData(form),
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
        })
            .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
            .then(function (res) {
                if (!res.ok) return showErrors(res.data.errors);
                var c = res.data;
                document.querySelectorAll('select[name="customer"]').forEach(function (select) {
                    var opt = document.createElement("option");
                    opt.value = c.pk;
                    opt.textContent = c.label;
                    opt.setAttribute("data-ship", c.ship);
                    opt.setAttribute("data-address", c.address);
                    opt.setAttribute("data-lat", c.lat);
                    opt.setAttribute("data-lng", c.lng);
                    select.appendChild(opt);
                });
                if (target) {
                    target.value = String(c.pk);
                    target.dispatchEvent(new Event("change", { bubbles: true }));
                }
                form.reset();
                form.querySelectorAll("[data-map-lat], [data-map-lng]").forEach(function (i) { i.value = ""; i.dispatchEvent(new Event("input")); });
                errorBox.hidden = true;
                modal.hide();
            })
            .catch(function () { showErrors({}); })
            .then(function () { save.disabled = false; });
    });
})();
