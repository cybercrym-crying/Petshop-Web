from django.db import models

from common.models import TimeStampedModel


class FaqEntry(TimeStampedModel):
    """Satu pertanyaan yang sering ditanya + jawabannya (dikelola admin)."""

    question = models.CharField("Pertanyaan", max_length=200)
    answer = models.TextField(
        "Jawaban",
        help_text="Boleh memakai [[layanan]] (daftar harga layanan) dan [[wa]] (nomor WhatsApp admin).",
    )
    keywords = models.CharField(
        "Kata kunci",
        max_length=500,
        blank=True,
        default="",
        help_text="Pisahkan dengan koma, mis. ongkir, ongkos kirim, biaya kirim",
    )
    link_url = models.CharField("Tautan", max_length=200, blank=True, default="")
    link_label = models.CharField("Teks tautan", max_length=60, blank=True, default="")
    order = models.PositiveSmallIntegerField("Urutan", default=100)
    is_active = models.BooleanField("Aktif", default=True)
    is_quick = models.BooleanField(
        "Tampil sebagai pilihan cepat", default=False,
        help_text="Muncul sebagai tombol saat chat dibuka.",
    )
    hits = models.PositiveIntegerField("Dipakai", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "FAQ chatbot"
        verbose_name_plural = "FAQ chatbot"

    def __str__(self):
        return self.question

    @property
    def keyword_list(self):
        return [k.strip() for k in self.keywords.split(",") if k.strip()]


class ChatLog(models.Model):
    """Pertanyaan pengunjung; yang tidak terjawab jadi bahan FAQ baru."""

    message = models.CharField(max_length=300)
    matched = models.ForeignKey(
        FaqEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"
    )
    intent = models.CharField(max_length=30, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "log chatbot"
        verbose_name_plural = "log chatbot"

    @property
    def answered(self):
        return bool(self.matched_id or self.intent)
