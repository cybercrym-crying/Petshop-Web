/* Hitung selisih uang (kas shift, setoran COD): tampilkan saat kasir mengetik, catatan jadi wajib bila ada selisih. */
(function () {
  function rupiah(n) { return n.toLocaleString("id-ID"); }
  document.querySelectorAll("[data-cash-diff]").forEach(function (form) {
    var expected = parseInt(form.getAttribute("data-expected"), 10) || 0;
    var input = form.querySelector("[data-cash-input]");
    var note = form.querySelector("[data-cash-note]");
    var box = form.querySelector("[data-cash-result]");
    var tpl = document.querySelector("template[data-cash-texts]");
    if (!input || !box || !tpl) return;
    var texts = {};
    tpl.content.querySelectorAll("[data-k]").forEach(function (el) { texts[el.getAttribute("data-k")] = el.textContent; });
    function update() {
      var raw = (input.value || "").replace(/\D/g, "");
      if (!raw) { box.hidden = true; if (note) note.required = false; return; }
      var diff = parseInt(raw, 10) - expected;
      var key = diff === 0 ? "ok" : (diff < 0 ? "less" : "more");
      box.hidden = false;
      box.classList.toggle("is-ok", diff === 0);
      box.classList.toggle("is-gold", diff !== 0);
      box.querySelector("i").className = "bi " + (diff === 0 ? "bi-check2-circle" : "bi-exclamation-triangle");
      box.querySelector("span").textContent = texts[key].replace("%(n)s", rupiah(Math.abs(diff)));
      if (note) note.required = diff !== 0;
    }
    input.addEventListener("input", update);
    update();
  });
})();
