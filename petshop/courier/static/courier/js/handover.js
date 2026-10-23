/*
 * Serah terima: langkah 2 (foto) baru terbuka setelah QR / kode penerima dicek server.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  var form = document.querySelector("[data-handover]");
  if (!form) return;
  var input = form.querySelector("#handover-code");
  var status = form.querySelector("[data-check-status]");
  var stepScan = form.querySelector("[data-step-scan]");
  var stepPhoto = form.querySelector("[data-step-photo]");
  var checkBtn = form.querySelector("[data-check-code]");

  function check() {
    var code = input.value.trim();
    if (!code) return;
    var body = new FormData();
    body.append("code", code);
    status.textContent = tr("Mencocokkan…");
    status.classList.remove("is-error");
    fetch(form.getAttribute("data-check-url"), {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": form.getAttribute("data-csrf"), "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        status.textContent = data.message;
        status.classList.toggle("is-error", !data.ok);
        stepScan.classList.toggle("is-done", !!data.ok);
        stepPhoto.classList.toggle("is-locked", !data.ok);
        if (data.ok) {
          input.readOnly = true;
          var start = stepPhoto.querySelector("[data-cam-start]");
          if (start) start.click();
          stepPhoto.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      })
      .catch(function () {
        status.textContent = tr("Gagal mengecek, periksa sinyal lalu coba lagi.");
        status.classList.add("is-error");
      });
  }

  checkBtn.addEventListener("click", check);
  form.addEventListener("qr:found", check);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); check(); }
  });
})();
