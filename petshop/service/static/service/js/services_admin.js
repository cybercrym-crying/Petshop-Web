// Jenis Layanan (admin): saring kartu layanan dan penyunting tahapan kerja.
(function () {
    document.documentElement.classList.add("svx-js");

    // ---------- Saring kartu: Semua / Tampil / Disembunyikan ----------
    var nav = document.querySelector("[data-svx-filter]");
    if (nav) {
        var cards = document.querySelectorAll(".svx-card");
        var none = document.querySelector(".svx-none");
        nav.addEventListener("click", function (e) {
            var btn = e.target.closest("button[data-show]");
            if (!btn) return;
            nav.querySelectorAll("button").forEach(function (b) {
                var on = b === btn;
                b.classList.toggle("is-on", on);
                b.setAttribute("aria-pressed", on ? "true" : "false");
            });
            var want = btn.dataset.show, shown = 0;
            cards.forEach(function (c) {
                var show = want === "all" || c.dataset.state === want;
                c.hidden = !show;
                if (show) shown++;
            });
            if (none) none.hidden = shown > 0;
        });
    }

    // ---------- Penyunting tahapan ----------
    var form = document.querySelector("[data-steps-form]");
    if (!form) return;
    var list = form.querySelector("[data-steps-list]");
    var tpl = form.querySelector("[data-step-template]");
    var total = form.querySelector('input[name$="-TOTAL_FORMS"]');
    var preview = document.querySelector("[data-steps-preview]");
    var previewEmpty = document.querySelector(".svx-preview-empty");

    function rows() { return Array.prototype.slice.call(list.querySelectorAll("[data-step]")); }
    function isDeleted(row) { var d = row.querySelector("[data-del]"); return !!(d && d.checked); }
    function hasName(row) { return row.querySelector("[data-name]").value.trim() !== ""; }

    // Nomor urut 1..n untuk tahap yang terisi. Baris kosong tetap memakai nilai awalnya
    // supaya Django menganggapnya tidak diubah (dan mengabaikannya).
    function renumber() {
        var n = 0, names = [];
        rows().forEach(function (row) {
            var pos = row.querySelector("[data-pos]");
            var no = row.querySelector("[data-no]");
            var counted = hasName(row) && !isDeleted(row);
            row.classList.toggle("is-del", isDeleted(row));
            row.classList.toggle("is-blank", !hasName(row));
            if (counted) {
                n += 1;
                pos.value = n;
                no.textContent = n;
                names.push({ name: row.querySelector("[data-name]").value.trim(), photo: row.querySelector("[data-photo]").checked });
            } else {
                pos.value = row.hasAttribute("data-saved") ? (pos.value || pos.dataset.initial) : pos.dataset.initial;
                no.textContent = isDeleted(row) ? "–" : "+";
            }
        });
        if (preview) {
            preview.innerHTML = "";
            names.forEach(function (s, i) {
                var li = document.createElement("li");
                li.className = "sg-step";
                var no = document.createElement("span");
                no.className = "sg-step__n";
                no.textContent = i + 1;
                var b = document.createElement("b");
                b.textContent = s.name;
                li.appendChild(no);
                li.appendChild(b);
                if (s.photo) {
                    var cam = document.createElement("i");
                    cam.className = "bi bi-camera-fill svx-flow__cam";
                    cam.setAttribute("aria-hidden", "true");
                    li.appendChild(cam);
                }
                preview.appendChild(li);
            });
            if (previewEmpty) previewEmpty.hidden = names.length > 0;
        }
    }

    list.addEventListener("click", function (e) {
        var move = e.target.closest("[data-move]");
        var clear = e.target.closest("[data-clear]");
        if (move) {
            var row = move.closest("[data-step]");
            var all = rows();
            var i = all.indexOf(row);
            var j = i + Number(move.dataset.move);
            if (j < 0 || j >= all.length) return;
            if (Number(move.dataset.move) < 0) list.insertBefore(row, all[j]);
            else list.insertBefore(all[j], row);
            renumber();
            move.focus();
        } else if (clear) {
            var r = clear.closest("[data-step]");
            r.querySelector("[data-name]").value = "";
            r.querySelector("[data-photo]").checked = true;
            renumber();
        }
    });
    list.addEventListener("input", renumber);
    list.addEventListener("change", renumber);

    var add = form.querySelector("[data-step-add]");
    if (add && tpl && total) {
        add.addEventListener("click", function () {
            var index = Number(total.value);
            var holder = document.createElement("ol");
            holder.innerHTML = tpl.innerHTML.replace(/__prefix__/g, index);
            var row = holder.firstElementChild;
            list.appendChild(row);
            total.value = index + 1;
            renumber();
            row.querySelector("[data-name]").focus();
        });
    }
    renumber();
})();
