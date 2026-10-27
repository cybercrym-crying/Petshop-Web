/*
 * Layar kasir: hitung total, kembalian, dan tampilkan kolom sesuai pilihan.
 * Angka di layar hanya bantuan; server menghitung ulang semuanya saat Bayar.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  var form = document.querySelector("[data-pos-form]");
  if (!form) return;

  var subtotal = parseInt(form.getAttribute("data-subtotal"), 10) || 0;
  var taxPct = parseFloat(form.getAttribute("data-tax")) || 0;
  var limit = parseInt(form.getAttribute("data-limit"), 10) || 0;
  var isAdmin = form.getAttribute("data-admin") === "1";

  function field(name) { return form.querySelector('[data-money="' + name + '"]'); }
  function out(name) { return form.querySelector('[data-out="' + name + '"]'); }
  function money(name) {
    var el = field(name);
    return el ? parseInt((el.value || "").replace(/\D/g, ""), 10) || 0 : 0;
  }
  function rp(n) { return "Rp " + Math.abs(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  function setMoney(name, n) { var el = field(name); if (el) el.value = n ? rp(n).slice(3) : ""; }
  function isDelivery() {
    var r = form.querySelector("[data-fulfillment]:checked");
    return r && r.value === "DIANTAR";
  }
  function row(name, show) { var el = form.querySelector('[data-row="' + name + '"]'); if (el) el.hidden = !show; }

  // Ongkir otomatis dari titik rumah pelanggan (dihitung server, sama seperti saat Bayar);
  // kasir tetap bisa menimpanya dengan mengisi kolom ongkir.
  function autoShipping() {
    var select = form.querySelector('select[name="customer"]');
    var opt = select && select.options[select.selectedIndex];
    return opt ? parseInt(opt.getAttribute("data-ship"), 10) || 0 : 0;
  }
  function total() {
    var discount = Math.min(money("discount"), subtotal);
    var tax = Math.round((subtotal - discount) * taxPct / 100);
    var shipping = isDelivery() ? (money("shipping") || autoShipping()) : 0;
    return { discount: discount, tax: tax, shipping: shipping, total: subtotal - discount + tax + shipping };
  }

  function refresh() {
    var t = total();
    var delivery = isDelivery();
    form.querySelectorAll("[data-delivery-fields]").forEach(function (el) { el.hidden = !delivery; });
    // COD (bayar saat sampai) hanya untuk pesanan diantar; kolom bayar sekarang disembunyikan.
    var codPicked = form.querySelector('[data-cod][value="1"]:checked');
    form.querySelectorAll("[data-cod]").forEach(function (el) { el.disabled = !delivery; });
    var cod = delivery && !!codPicked;
    var codHint = form.querySelector("[data-cod-hint]");
    if (codHint) codHint.hidden = !cod;
    var payNow = form.querySelector("[data-pay-now]");
    if (payNow) payNow.hidden = cod;
    var label = form.querySelector("[data-pay-label]");
    if (label) {
      if (!label.hasAttribute("data-pay-text")) label.setAttribute("data-pay-text", label.textContent);
      label.textContent = cod ? label.getAttribute("data-cod-label") : label.getAttribute("data-pay-text");
    }
    var customer = form.querySelector('[name="customer"]');
    form.querySelectorAll("[data-walkin-fields]").forEach(function (el) { el.hidden = !!(customer && customer.value); });

    row("discount", t.discount > 0);
    if (out("discount")) out("discount").textContent = "- " + rp(t.discount);
    if (out("tax")) out("tax").textContent = rp(t.tax);
    var shipField = field("shipping");
    if (shipField) {
      if (!shipField.hasAttribute("data-placeholder")) shipField.setAttribute("data-placeholder", shipField.placeholder);
      var auto = autoShipping();
      shipField.placeholder = auto ? tr("Ongkir otomatis {n}", { n: rp(auto) }) : shipField.getAttribute("data-placeholder");
    }
    row("shipping", delivery && t.shipping > 0);
    if (out("shipping")) out("shipping").textContent = rp(t.shipping);
    out("total").textContent = rp(t.total) + (delivery && !t.shipping ? " + " + tr("ongkir") : "");
    var bar = document.querySelector("[data-paybar-total]");
    if (bar) bar.textContent = out("total").textContent;
    var payBtn = form.querySelector("[data-pay-total]");
    if (payBtn) payBtn.textContent = out("total").textContent;

    var warn = form.querySelector("[data-discount-warn]");
    if (warn) warn.hidden = isAdmin || t.discount <= limit;

    var noncash = money("transfer") + money("qris");
    var box = form.querySelector("[data-noncash]");
    if (box) box.hidden = noncash === 0;

    var cashDue = t.total - noncash;
    var change = money("cash") - Math.max(cashDue, 0);
    var changeRow = form.querySelector("[data-change-row]");
    changeRow.hidden = cod;
    var short = change < 0 || cashDue < 0;
    changeRow.classList.toggle("is-short", short);
    if (cashDue < 0) {
      out("change-label").textContent = tr("Non-tunai lebih");
      out("change").textContent = rp(-cashDue);
    } else {
      out("change-label").textContent = change < 0 ? tr("Kurang") : tr("Kembalian");
      out("change").textContent = rp(change);
    }
  }

  form.addEventListener("input", function (e) {
    var el = e.target;
    if (el.hasAttribute("data-money")) {
      var digits = el.value.replace(/\D/g, "");
      el.value = digits ? rp(parseInt(digits, 10)).slice(3) : "";
    }
    refresh();
  });
  form.addEventListener("change", refresh);

  form.querySelectorAll("[data-pay-exact]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var t = total().total;
      var kind = btn.getAttribute("data-pay-exact");
      if (kind === "cash") {
        setMoney("cash", Math.max(t - money("transfer") - money("qris"), 0));
      } else {
        ["cash", "transfer", "qris"].forEach(function (k) { setMoney(k, k === kind ? t : 0); });
      }
      refresh();
    });
  });

  refresh();
})();
