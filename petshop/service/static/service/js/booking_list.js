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

// Buat booking: tampilkan daftar layanan dulu; groomer dan isian lain muncul setelah layanan dipilih.
(function () {
    var form = document.querySelector("[data-bk-new]");
    if (!form) return;
    var change = form.querySelector("[data-bk-change]");
    var type = form.querySelector("[data-bk-type]");
    var rest = form.querySelector("[data-bk-rest]");

    function picked() {
        return form.querySelector('input[name="service"]:checked');
    }
    var sum = form.querySelector("[data-bk-sum]");
    var sumNote = form.querySelector("[data-bk-sum-note]");
    function show() {
        var input = picked();
        form.classList.toggle("is-picking", !input);
        form.classList.toggle("is-picked", !!input);
        if (change) change.hidden = !input;
        if (sum) {
            var price = input ? +input.closest("[data-bk-svc]").getAttribute("data-price") : NaN;
            sum.textContent = isNaN(price) ? "\u2014" : "Rp " + price.toLocaleString("id-ID");
        }
        renderSlots();
    }

    // Jadwal: tanggal tidak bisa mundur + pilihan jam per 30 menit. Jam yang sudah lewat, atau yang
    // membuat layanan selesai setelah jam tutup, tidak bisa dipilih. Waktu "sekarang" dari server (WITA).
    var dateInput = form.querySelector("[data-bk-date]");
    var slotsBox = form.querySelector("[data-bk-slots]");
    var schedule = form.querySelector("[data-bk-schedule]");
    var slotEmpty = form.querySelector("[data-bk-slot-empty]");
    var slotError = form.querySelector("[data-bk-slot-error]");
    var nowIso = form.getAttribute("data-now") || "";
    var chosenTime = "";
    function toMin(text) {
        var p = text.split(":");
        return +p[0] * 60 + +p[1];
    }
    function toText(m) {
        return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
    }
    function syncSchedule() {
        if (!schedule) return;
        schedule.value = dateInput.value && chosenTime ? dateInput.value + "T" + chosenTime : "";
        if (chosenTime && slotError) slotError.hidden = true;
    }
    function renderSlots() {
        if (!slotsBox || !dateInput) return;
        var today = nowIso.slice(0, 10);
        if (!dateInput.value || dateInput.value < today) dateInput.value = today;
        var open = toMin(form.getAttribute("data-open"));
        var close = toMin(form.getAttribute("data-close"));
        var svc = picked();
        var duration = svc ? +svc.closest("[data-bk-svc]").getAttribute("data-duration") || 0 : 0;
        // Pelanggan yang baru datang masih boleh dicatat sampai 15 menit setelah jamnya lewat.
        var earliest = dateInput.value === today ? toMin(nowIso.slice(11, 16)) - 15 : -1;
        slotsBox.textContent = "";
        var any = false;
        var kept = false;
        for (var m = open; m + duration <= close; m += 30) {
            var text = toText(m);
            var label = document.createElement("label");
            label.className = "bk-time";
            var radio = document.createElement("input");
            radio.type = "radio";
            radio.name = "bk_slot";
            radio.value = text;
            radio.disabled = m < earliest;
            var span = document.createElement("span");
            span.textContent = text.replace(":", ".");
            label.appendChild(radio);
            label.appendChild(span);
            slotsBox.appendChild(label);
            if (!radio.disabled) any = true;
            if (text === chosenTime && !radio.disabled) {
                radio.checked = true;
                kept = true;
            }
        }
        if (!kept) chosenTime = "";
        if (slotEmpty) slotEmpty.hidden = any;
        syncSchedule();
    }
    if (slotsBox) {
        slotsBox.addEventListener("change", function (e) {
            if (e.target.name !== "bk_slot") return;
            chosenTime = e.target.value;
            syncSchedule();
        });
    }
    if (dateInput) dateInput.addEventListener("change", renderSlots);
    form.addEventListener("submit", function (e) {
        if (schedule && !schedule.value) {
            e.preventDefault();
            if (slotError) slotError.hidden = false;
            slotsBox.scrollIntoView({ block: "center", behavior: "smooth" });
        }
    });

    form.querySelectorAll('input[name="service"]').forEach(function (input) {
        // "click" juga jalan saat layanan yang sama dipilih ulang setelah "Ganti layanan".
        input.addEventListener("click", function () {
            var pet = input.closest("[data-bk-svc]").getAttribute("data-pet");
            if (type && pet && pet !== "SEMUA") type.value = pet;
            show();
            var first = rest && rest.querySelector('input[name="groomer"]:checked');
            if (first) first.focus();
        });
    });
    if (change) {
        change.addEventListener("click", function () {
            form.classList.remove("is-picked");
            form.classList.add("is-picking");
            change.hidden = true;
            var input = picked();
            if (input) input.focus();
        });
    }
    // Antar-jemput: peta & alamat muncul bila jemput/antar dicentang; COD hanya bila diantar pulang.
    var trips = form.querySelectorAll("[data-bk-trip]");
    var tripBox = form.querySelector("[data-bk-trip-box]");
    var back = form.querySelector("[data-bk-return]");
    var cod = form.querySelector('[data-bk-cod] input');
    var customer = form.querySelector('select[name="customer"]');
    function syncTrip() {
        var any = Array.prototype.some.call(trips, function (c) { return c.checked; });
        if (sumNote) sumNote.hidden = !any;
        if (tripBox) {
            tripBox.hidden = !any;
            var address = tripBox.querySelector('textarea[name="address"]');
            if (address) address.required = any;
            if (any) {
                var map = tripBox.querySelector("[data-map-picker]");
                if (map && map._map) window.setTimeout(function () { map._map.invalidateSize(); }, 50);
            }
        }
        if (cod) {
            cod.disabled = !(back && back.checked);
            var hint = form.querySelector("[data-bk-cod-hint]");
            if (hint) hint.hidden = !cod.disabled;
            if (cod.disabled && cod.checked) {
                cod.checked = false;
                form.querySelector('input[name="payment_choice"][value="NANTI"]').checked = true;
            }
        }
    }
    function fillFromCustomer() {
        if (!customer || !tripBox) return;
        var opt = customer.options[customer.selectedIndex];
        if (!opt || !opt.value) return;
        var lat = tripBox.querySelector("[data-map-lat]");
        var lng = tripBox.querySelector("[data-map-lng]");
        var address = tripBox.querySelector('textarea[name="address"]');
        // Isi dari data pelanggan; tetap bisa diubah kasir.
        if (address) address.value = opt.getAttribute("data-address") || "";
        if (lat && lng) {
            lat.value = opt.getAttribute("data-lat") || "";
            lng.value = opt.getAttribute("data-lng") || "";
            lat.dispatchEvent(new Event("input", { bubbles: true }));
        }
    }
    trips.forEach(function (c) { c.addEventListener("change", syncTrip); });
    if (customer) customer.addEventListener("change", fillFromCustomer);

    var modal = form.closest(".modal");
    if (modal) {
        modal.addEventListener("hidden.bs.modal", function () {
            // Ditutup sementara untuk menambah pelanggan baru: isian tetap.
            if (modal.dataset.qcKeep) return;
            form.reset();
            chosenTime = "";
            show();
            syncTrip();
        });
    }
    show();
    syncTrip();
})();
