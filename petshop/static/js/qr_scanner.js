/*
 * Pemindai QR dari kamera web. BarcodeDetector bawaan browser dipakai bila ada,
 * selain itu jsQR (static/vendor/jsqr) membaca gambar dari <video>.
 *
 *   <div data-qr-scanner data-target="#id_code" [data-autosubmit]>
 *     <video data-qr-video playsinline muted hidden></video>
 *     <p data-qr-status></p>
 *     <button type="button" data-qr-start>Scan QR</button>
 *   </div>
 *
 * data-formats="qr_code,ean_13,code_128" (opsional) menambah format barcode untuk
 * BarcodeDetector; jsQR hanya membaca QR, jadi barcode batang perlu browser yang
 * mendukung BarcodeDetector atau scanner USB.
 *
 * Hasil scan diisi ke input target lalu event "qr:found" (detail.text) dikirim dari
 * elemen scanner; dengan data-autosubmit form milik input langsung dikirim.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  function Scanner(root) {
    this.root = root;
    this.video = root.querySelector("[data-qr-video]");
    this.status = root.querySelector("[data-qr-status]");
    this.btn = root.querySelector("[data-qr-start]");
    this.target = document.querySelector(root.getAttribute("data-target"));
    this.canvas = document.createElement("canvas");
    this.stream = null;
    this.timer = null;
    this.detector = null;
    this.label = this.btn.textContent;
    if ("BarcodeDetector" in window) {
      try { this.detector = new window.BarcodeDetector({ formats: (root.getAttribute("data-formats") || "qr_code").split(",") }); } catch (e) { this.detector = null; }
    }
    var self = this;
    this.btn.addEventListener("click", function () {
      if (self.stream) self.stop(); else self.start();
    });
    if (root.hasAttribute("data-autostart")) this.start();
  }

  Scanner.prototype.say = function (text, bad) {
    if (!this.status) return;
    this.status.textContent = text;
    this.status.classList.toggle("is-error", !!bad);
  };

  Scanner.prototype.start = function () {
    var self = this;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.say(tr("Kamera tidak tersedia di browser ini. Ketik kodenya secara manual."), true);
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
      .then(function (stream) {
        self.stream = stream;
        self.video.srcObject = stream;
        self.video.hidden = false;
        self.btn.textContent = tr("Tutup kamera");
        self.say(tr("Arahkan kamera ke QR…"));
        return self.video.play().then(function () { self.loop(); });
      })
      .catch(function () {
        self.say(tr("Kamera tidak bisa dibuka (izin ditolak / bukan HTTPS). Ketik kodenya secara manual."), true);
      });
  };

  Scanner.prototype.stop = function () {
    window.clearTimeout(this.timer);
    if (this.stream) this.stream.getTracks().forEach(function (t) { t.stop(); });
    this.stream = null;
    this.video.hidden = true;
    this.btn.textContent = this.label;
  };

  Scanner.prototype.found = function (text) {
    this.stop();
    if (this.target) this.target.value = text;
    this.say(tr("QR terbaca."));
    this.root.dispatchEvent(new CustomEvent("qr:found", { bubbles: true, detail: { text: text } }));
    if (this.root.hasAttribute("data-autosubmit") && this.target && this.target.form) {
      if (this.target.form.requestSubmit) this.target.form.requestSubmit();
      else this.target.form.submit();
    }
  };

  Scanner.prototype.loop = function () {
    var self = this;
    if (!this.stream) return;
    var next = function () { self.timer = window.setTimeout(function () { self.loop(); }, 250); };
    if (this.video.readyState < 2) return next();
    if (this.detector) {
      this.detector.detect(this.video).then(function (codes) {
        if (codes.length) self.found(codes[0].rawValue); else next();
      }).catch(function () { self.detector = null; next(); });
      return;
    }
    if (!window.jsQR) return next();
    var w = this.video.videoWidth, h = this.video.videoHeight;
    var scale = Math.min(1, 640 / Math.max(w, h));
    this.canvas.width = Math.round(w * scale);
    this.canvas.height = Math.round(h * scale);
    var ctx = this.canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
    var img = ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
    var code = window.jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
    if (code && code.data) this.found(code.data); else next();
  };

  document.querySelectorAll("[data-qr-scanner]").forEach(function (root) { new Scanner(root); });
})();
