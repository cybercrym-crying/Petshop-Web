/*
 * Widget chatbot FAQ. Riwayat percakapan disimpan di sessionStorage
 * (hilang saat tab ditutup) supaya tetap ada saat pindah halaman.
 */
/* Terjemahan teks JS (lihat static/js/i18n.js). */
function tr(text, vars) { return window.petT ? window.petT(text, vars) : text; }

(function () {
  "use strict";

  var root = document.querySelector("[data-chatbot]");
  if (!root) return;

  var KEY = "seelly_chatbot_v1";
  var panel = root.querySelector(".cb-panel");
  var log = root.querySelector("[data-cb-log]");
  var form = root.querySelector("[data-cb-form]");
  var input = form.querySelector("input");
  var sendBtn = form.querySelector("button");
  var launcher = root.querySelector(".cb-launcher");
  var startUrl = root.getAttribute("data-start-url");
  var askUrl = root.getAttribute("data-ask-url");
  var csrf = root.getAttribute("data-csrf");
  var state = load();
  var busy = false;

  function load() {
    try {
      var raw = JSON.parse(sessionStorage.getItem(KEY));
      if (raw && Array.isArray(raw.items)) return raw;
    } catch (e) {}
    return { open: false, items: [], wa: "" };
  }

  function save() {
    try {
      state.items = state.items.slice(-60);
      sessionStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) {}
  }

  function safeUrl(url) {
    url = String(url || "");
    return /^(\/(?!\/)|https:\/\/)/.test(url) ? url : "";
  }

  function scrollDown() {
    log.scrollTop = log.scrollHeight;
  }

  function renderItem(item) {
    if (item.type === "user" || item.type === "bot") {
      var bubble = document.createElement("div");
      bubble.className = "cb-msg cb-msg--" + item.type;
      bubble.textContent = item.text;
      log.appendChild(bubble);
      return;
    }
    if (item.type === "actions") {
      var box = document.createElement("div");
      box.className = "cb-actions";
      var link = item.link && safeUrl(item.link.url);
      if (link) {
        var a = document.createElement("a");
        a.className = "cb-link";
        a.href = link;
        a.textContent = item.link.label || "Buka";
        box.appendChild(a);
      }
      if (item.fallback && state.wa) {
        var wa = document.createElement("a");
        wa.className = "cb-wa";
        wa.href = safeUrl(state.wa);
        wa.target = "_blank";
        wa.rel = "noopener";
        wa.innerHTML = '<i class="fab fa-whatsapp" aria-hidden="true"></i>';
        wa.appendChild(document.createTextNode(" Chat admin"));
        box.appendChild(wa);
      }
      (item.chips || []).forEach(function (chip) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "cb-chip";
        b.textContent = chip.question;
        if (chip.id) b.setAttribute("data-faq", chip.id);
        b.setAttribute("data-question", chip.question);
        box.appendChild(b);
      });
      if (box.childNodes.length) log.appendChild(box);
    }
  }

  function push(item) {
    state.items.push(item);
    save();
    renderItem(item);
    scrollDown();
  }

  function renderAll() {
    log.textContent = "";
    state.items.forEach(renderItem);
    scrollDown();
  }

  function typing(on) {
    var el = log.querySelector(".cb-typing");
    if (on && !el) {
      el = document.createElement("div");
      el.className = "cb-typing";
      el.setAttribute("aria-label", tr("Asisten sedang mengetik"));
      el.innerHTML = "<span></span><span></span><span></span>";
      log.appendChild(el);
      scrollDown();
    } else if (!on && el) {
      el.remove();
    }
  }

  function begin() {
    if (state.items.length) return;
    typing(true);
    fetch(startUrl, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        typing(false);
        state.wa = data.wa || "";
        push({ type: "bot", text: data.greeting });
        push({ type: "actions", chips: data.quick || [] });
      })
      .catch(function () {
        typing(false);
        push({ type: "bot", text: "Maaf, chat sedang tidak bisa dimuat. Coba lagi sebentar." });
      });
  }

  function ask(text, faqId) {
    if (busy) return;
    text = String(text || "").trim();
    if (!text) return;
    busy = true;
    sendBtn.disabled = true;
    push({ type: "user", text: text });
    typing(true);
    var body = faqId ? { faq: faqId } : { message: text };
    fetch(askUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (data.wa) state.wa = data.wa;
        typing(false);
        push({ type: "bot", text: data.answer });
        push({
          type: "actions",
          link: data.link,
          fallback: !!data.fallback,
          chips: (data.suggestions || []).map(function (q) {
            return { question: q };
          }),
        });
      })
      .catch(function () {
        typing(false);
        push({ type: "bot", text: "Maaf, koneksi bermasalah. Silakan coba lagi atau hubungi admin lewat WhatsApp." });
        push({ type: "actions", fallback: true });
      })
      .then(function () {
        busy = false;
        sendBtn.disabled = false;
      });
  }

  function setOpen(open) {
    state.open = open;
    save();
    panel.hidden = !open;
    root.classList.toggle("is-open", open);
    root.querySelectorAll("[data-cb-toggle]").forEach(function (b) {
      b.setAttribute("aria-expanded", open ? "true" : "false");
    });
    launcher.setAttribute("aria-label", open ? tr("Tutup chat bantuan") : tr("Buka chat bantuan"));
    if (open) {
      renderAll();
      begin();
      // Di HP jangan langsung munculkan keyboard.
      if (window.matchMedia("(min-width: 576px)").matches) input.focus();
    }
  }

  root.addEventListener("click", function (event) {
    if (event.target.closest("[data-cb-toggle]")) {
      setOpen(panel.hidden);
      if (panel.hidden) launcher.focus();
      return;
    }
    if (event.target.closest("[data-cb-reset]")) {
      state.items = [];
      save();
      renderAll();
      begin();
      return;
    }
    var chip = event.target.closest(".cb-chip");
    if (chip) ask(chip.getAttribute("data-question"), chip.getAttribute("data-faq"));
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value;
    input.value = "";
    ask(text);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !panel.hidden) {
      setOpen(false);
      launcher.focus();
    }
  });

  if (state.open) setOpen(true);
  else launcher.setAttribute("aria-label", tr("Buka chat bantuan"));
})();
