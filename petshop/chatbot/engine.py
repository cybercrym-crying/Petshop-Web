"""Mesin jawab sederhana untuk chatbot FAQ (tanpa AI berbayar).

Cara kerja:
1. Intent khusus dicek dulu: nomor resi (langsung cek status pesanan),
   salam, dan ucapan terima kasih.
2. Selain itu, setiap FAQ aktif diberi skor: frasa kata kunci yang muncul utuh
   di pesan bernilai besar, kata yang sama dengan pertanyaan/kata kunci FAQ
   bernilai 1, dan kata yang mirip (salah ketik) bernilai sebagian.
3. Skor tertinggi di atas ambang = jawaban; FAQ berikutnya jadi saran.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

MIN_SCORE = 2.0
SUGGESTION_SCORE = 1.0
MAX_SUGGESTIONS = 3
MAX_MESSAGE = 300

STOPWORDS = {
    "apa", "apakah", "yang", "di", "ke", "dari", "dan", "atau", "itu", "ini",
    "saya", "aku", "gue", "gw", "kami", "kita", "anda", "kamu", "kak", "kakak",
    "min", "mimin", "admin", "gan", "sis", "bang", "mas", "mbak", "bu", "pak",
    "bisa", "boleh", "mau", "ingin", "pengen", "pingin", "tolong", "mohon",
    "gimana", "bagaimana", "caranya", "cara", "kalau", "kalo", "klo", "kok",
    "ya", "yah", "dong", "deh", "sih", "nih", "nya", "kah", "lah", "ga", "gak",
    "nggak", "tidak", "tdk", "udah", "sudah", "belum", "blm", "ada", "adakah",
    "untuk", "buat", "utk", "dengan", "dgn", "pada", "dalam", "juga", "lagi",
    "berapa", "brp", "dimana", "mana", "siapa", "kenapa", "mengapa",
    "tanya", "nanya", "info", "informasi", "halo", "hai", "hi", "hallo", "permisi",
    "the", "a", "is", "how", "what",
    "hewan", "peliharaan",  # terlalu umum di toko hewan, bikin salah cocok
}
SUFFIXES = ("nya", "kah", "lah", "pun", "kan", "in")  # "in": batalin, kirimin

GREETINGS = {"halo", "hai", "hi", "hallo", "hello", "pagi", "siang", "sore", "malam",
             "assalamualaikum", "permisi", "selamat", "p", "tes", "test"}
THANKS = ("terima kasih", "makasih", "thanks", "thank you", "trims", "tengkyu", "mksh")

RESI_RE = re.compile(r"\bPS[\s\-]?\d{6}[\s\-]?[A-Z0-9]{6}\b", re.IGNORECASE)


@dataclass
class Reply:
    answer: str
    link_url: str = ""
    link_label: str = ""
    suggestions: list = field(default_factory=list)
    matched: object = None  # FaqEntry atau None
    intent: str = ""
    fallback: bool = False  # tampilkan tombol "Chat admin"

    def as_json(self):
        return {
            "answer": self.answer,
            "link": {"url": self.link_url, "label": self.link_label} if self.link_url else None,
            "suggestions": self.suggestions,
            "fallback": self.fallback,
        }


def normalize(text):
    text = strip_tags(str(text or "")).lower()
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stem(word):
    """Pemangkas sangat ringan: akhiran partikel & informal (ongkirnya, batalin)."""
    for suffix in SUFFIXES:
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    if word.startswith("di") and len(word) > 6:  # dibatal -> batal, dikirim -> kirim
        word = word[2:]
    return word


def tokens(text):
    return [stem(w) for w in normalize(text).split() if w not in STOPWORDS and len(w) > 1]


def _similar(a, b):
    if a == b:
        return 1.0
    if min(len(a), len(b)) < 4:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score_entry(entry, text_norm, words):
    """Frasa kata kunci utuh = sinyal terkuat; kata yang cocok dengan kata kunci
    lebih berbobot daripada kata di judul pertanyaan; salah ketik dapat sebagian."""
    score = 0.0
    padded = f" {text_norm} "
    padded_stem = " " + " ".join(stem(w) for w in text_norm.split()) + " "
    question_vocab = set(tokens(entry.question))
    keyword_vocab = set()
    for keyword in entry.keyword_list:
        kw = normalize(keyword)
        if not kw:
            continue
        keyword_vocab.update(tokens(kw))
        kw_stem = " ".join(stem(w) for w in kw.split())
        if f" {kw} " in padded or f" {kw_stem} " in padded_stem:
            score += 2 + len(kw.split())
    for word in set(words):
        if word in keyword_vocab:
            score += 2
        elif word in question_vocab:
            score += 1
        elif max((_similar(word, v) for v in keyword_vocab), default=0) >= 0.84:
            score += 1.5
        elif max((_similar(word, v) for v in question_vocab), default=0) >= 0.84:
            score += 0.8
    return score


def fill_placeholders(text, wa_display):
    if "[[layanan]]" in text:
        from service.models import Service

        lines = [
            f"• {s.name} ({s.get_pet_type_display()}): Rp {s.price:,}".replace(",", ".")
            for s in Service.objects.active()
        ]
        text = text.replace("[[layanan]]", "\n".join(lines) or "(belum ada layanan aktif)")
    return text.replace("[[wa]]", wa_display)


def _order_reply(raw):
    from transaction.models import Order, OrderStatus, normalize_tracking_number

    code = normalize_tracking_number(raw)
    order = Order.objects.filter(tracking_number=code).first() if code else None
    if order is None:
        return Reply(
            answer=_("Resi %(code)s tidak ditemukan. Periksa kembali nomor resinya ya (contoh: PS-261022-K7M2QX).") % {"code": raw.upper()},
            intent="resi",
            fallback=True,
        )
    notes = {
        OrderStatus.PENDING: _("Pesanan sedang menunggu konfirmasi admin."),
        OrderStatus.CONFIRMED: _("Pesanan sudah dikonfirmasi dan sedang disiapkan."),
        OrderStatus.ON_DELIVERY: _("Pesanan sedang diantar kurir. Posisi kurir bisa dilihat langsung di peta."),
        OrderStatus.DELIVERED: _("Pesanan sudah sampai. Foto bukti pengiriman ada di halaman lacak."),
        OrderStatus.CANCELLED: _("Pesanan ini dibatalkan."),
    }
    return Reply(
        answer=(
            _("Status pesanan %(code)s: %(status)s.") % {"code": order.tracking_number, "status": order.get_order_status_display()}
            + "\n" + notes.get(order.order_status, "")
        ).strip(),
        link_url=reverse("customer:track_detail", args=[order.tracking_number]),
        link_label=_("Buka halaman lacak"),
        intent="resi",
    )


def answer(message, faqs, wa_display):
    """faqs: iterable FaqEntry aktif. Mengembalikan Reply."""
    message = (message or "").strip()[:MAX_MESSAGE]
    text_norm = normalize(message)
    if not text_norm:
        return Reply(answer=_("Silakan ketik pertanyaan Anda 🙂"), intent="empty")

    resi = RESI_RE.search(message)
    if resi:
        return _order_reply(resi.group(0))

    raw_words = text_norm.split()
    if any(t in text_norm for t in THANKS) and len(raw_words) <= 5:
        return Reply(answer=_("Sama-sama! Senang bisa membantu. 🐾"), intent="thanks")

    words = tokens(message)
    if not words and raw_words and set(raw_words) <= GREETINGS | STOPWORDS:
        return Reply(
            answer=_("Halo! Saya asisten Seelly Petshop. Silakan pilih pertanyaan di bawah atau ketik pertanyaan Anda."),
            intent="greeting",
        )

    faqs = list(faqs)
    ranked = sorted(
        ((score_entry(f, text_norm, words), f) for f in faqs),
        key=lambda pair: (-pair[0], pair[1].order, pair[1].pk),
    )
    best_score, best = ranked[0] if ranked else (0, None)
    if best is None or best_score < MIN_SCORE:
        related = [f.question for s, f in ranked[:MAX_SUGGESTIONS] if s >= SUGGESTION_SCORE]
        return Reply(
            answer=(
                _("Maaf, saya belum menemukan jawabannya.") + " "
                + (_("Mungkin maksud Anda salah satu pertanyaan di bawah?") + " " if related else "")
                + _("Anda juga bisa langsung chat admin di WhatsApp %(wa)s.") % {"wa": wa_display}
            ),
            suggestions=related,
            fallback=True,
        )
    related = [
        f.question for s, f in ranked[1 : MAX_SUGGESTIONS + 1] if s >= SUGGESTION_SCORE
    ]
    return Reply(
        answer=fill_placeholders(best.answer, wa_display),
        link_url=best.link_url,
        link_label=best.link_label or "Buka",
        suggestions=related,
        matched=best,
    )
