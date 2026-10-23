/*
 * Ambil foto langsung dari kamera web (tanpa unggah file manual).
 *
 *   <div data-camera [data-allow-file] [data-geo]>
 *     <video data-cam-video playsinline muted hidden></video>
 *     <img data-cam-preview alt="" hidden>
 *     <p data-cam-status></p>
 *     <button type="button" data-cam-start>…</button>
 *     <button type="button" data-cam-snap hidden>…</button>
 *     <button type="button" data-cam-retake hidden>…</button>
 *     <button type="button" data-cam-file hidden>…</button>     (hanya bila data-allow-file)
 *     <input type="file" name="photo" accept="image/*" capture="environment" data-cam-input hidden>
 *     <input type="hidden" name="latitude" data-cam-lat> <input type="hidden" name="longitude" data-cam-lng>
 *   </div>
 *
 * Foto dari kamera dimasukkan ke <input type=file> lewat DataTransfer, jadi form biasa
 * (multipart) tetap dipakai dan server memvalidasi file seperti unggahan lain.
 * Bila kamera tidak bisa dibuka (izin ditolak / bukan HTTPS), input dengan atribut
 * capture membuka aplikasi kamera HP sebagai cadangan.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  var MAX_SIDE = 1600;

  function Camera(root) {
    this.root = root;
    this.video = root.querySelector("[data-cam-video]");
    this.preview = root.querySelector("[data-cam-preview]");
    this.status = root.querySelector("[data-cam-status]");
    this.input = root.querySelector("[data-cam-input]");
    this.btnStart = root.querySelector("[data-cam-start]");
    this.btnSnap = root.querySelector("[data-cam-snap]");
    this.btnRetake = root.querySelector("[data-cam-retake]");
    this.btnFile = root.querySelector("[data-cam-file]");
    this.lat = root.querySelector("[data-cam-lat]");
    this.lng = root.querySelector("[data-cam-lng]");
    this.stream = null;
    this.bind();
    if (this.btnFile && root.hasAttribute("data-allow-file")) this.btnFile.hidden = false;
    if (root.hasAttribute("data-autostart")) this.start();
  }

  Camera.prototype.say = function (text, isError) {
    if (!this.status) return;
    this.status.textContent = text || "";
    this.status.classList.toggle("is-error", !!isError);
  };

  Camera.prototype.bind = function () {
    var self = this;
    this.btnStart.addEventListener("click", function () { self.start(); });
    this.btnSnap.addEventListener("click", function () { self.snap(); });
    this.btnRetake.addEventListener("click", function () { self.retake(); });
    if (this.btnFile) {
      this.btnFile.addEventListener("click", function () {
        self.input.removeAttribute("capture");
        self.input.click();
      });
    }
    this.input.addEventListener("change", function () {
      if (self.input.files && self.input.files[0]) self.showPreview(self.input.files[0]);
    });
    var form = this.root.closest("form");
    if (form) {
      form.addEventListener("submit", function (event) {
        if (self.input.hasAttribute("data-optional")) return;
        if (!self.input.files || !self.input.files.length) {
          event.preventDefault();
          self.say(tr("Ambil foto dulu sebelum mengirim."), true);
          self.btnStart.focus();
        }
      });
    }
  };

  Camera.prototype.start = function () {
    var self = this;
    if (this.useNative) {
      this.input.setAttribute("capture", "environment");
      this.input.click();
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.fallback(tr("Browser ini tidak bisa membuka kamera langsung."));
      return;
    }
    this.say(tr("Membuka kamera…"));
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false })
      .then(function (stream) {
        self.stream = stream;
        self.video.srcObject = stream;
        self.video.hidden = false;
        self.preview.hidden = true;
        self.btnStart.hidden = true;
        self.btnSnap.hidden = false;
        self.btnRetake.hidden = true;
        self.say(tr("Arahkan kamera lalu tekan Ambil foto."));
        return self.video.play();
      })
      .catch(function (err) {
        var denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
        self.fallback(denied ? tr("Izin kamera ditolak. Izinkan kamera di pengaturan browser.") : tr("Kamera tidak bisa dibuka."));
      });
    this.readLocation();
  };

  Camera.prototype.fallback = function (reason) {
    // Cadangan: input capture membuka kamera bawaan HP.
    this.useNative = true;
    this.stop();
    this.btnStart.hidden = false;
    this.btnSnap.hidden = true;
    this.say(reason + " Tekan tombol kamera lagi untuk memakai kamera HP.", true);
  };

  Camera.prototype.stop = function () {
    if (this.stream) this.stream.getTracks().forEach(function (t) { t.stop(); });
    this.stream = null;
    this.video.hidden = true;
  };

  Camera.prototype.snap = function () {
    var self = this;
    var w = this.video.videoWidth;
    var h = this.video.videoHeight;
    if (!w || !h) return;
    var scale = Math.min(1, MAX_SIDE / Math.max(w, h));
    var canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    var ctx = canvas.getContext("2d");
    ctx.drawImage(this.video, 0, 0, canvas.width, canvas.height);
    // Cap waktu di pojok foto sebagai jejak kapan foto diambil.
    var stamp = new Date().toLocaleString("id-ID");
    ctx.font = Math.round(canvas.width / 40) + "px sans-serif";
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(0, canvas.height - canvas.width / 22, canvas.width, canvas.width / 22);
    ctx.fillStyle = "#fff";
    ctx.fillText(stamp, 12, canvas.height - canvas.width / 70);
    canvas.toBlob(function (blob) {
      if (!blob) return;
      var file = new File([blob], "kamera-" + Date.now() + ".jpg", { type: "image/jpeg" });
      try {
        var dt = new DataTransfer();
        dt.items.add(file);
        self.input.files = dt.files;
      } catch (e) {
        self.fallback(tr("Browser tidak mendukung foto langsung."));
        return;
      }
      self.stop();
      self.showPreview(file);
    }, "image/jpeg", 0.85);
  };

  Camera.prototype.showPreview = function (file) {
    var url = URL.createObjectURL(file);
    this.preview.src = url;
    this.preview.hidden = false;
    this.btnSnap.hidden = true;
    this.btnStart.hidden = true;
    this.btnRetake.hidden = false;
    this.say(tr("Foto siap dikirim."));
    this.root.classList.add("has-photo");
  };

  Camera.prototype.retake = function () {
    this.input.value = "";
    this.preview.hidden = true;
    this.root.classList.remove("has-photo");
    this.start();
  };

  Camera.prototype.readLocation = function () {
    var self = this;
    if (!this.lat || !this.lng || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (pos) {
      self.lat.value = pos.coords.latitude.toFixed(6);
      self.lng.value = pos.coords.longitude.toFixed(6);
    }, function () {}, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });
  };

  document.querySelectorAll("[data-camera]").forEach(function (root) {
    new Camera(root);
  });
})();
