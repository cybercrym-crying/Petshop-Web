import json

from django.utils.translation import gettext as _
from django.contrib import messages
from django.db.models import Count, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from account.decorators import roleRequired
from account.models import Role
from store.models import StoreSettings

from . import engine
from .forms import FaqForm
from .models import ChatLog, FaqEntry

QUICK_LIMIT = 6
GREETING = (
    "Halo! 👋 Saya asisten Seelly Petshop. Pilih pertanyaan di bawah "
    "atau ketik pertanyaan Anda, misalnya “ongkir berapa?” atau nomor resi pesanan."
)


def _quick_questions():
    qs = FaqEntry.objects.filter(is_active=True)
    quick = list(qs.filter(is_quick=True)[:QUICK_LIMIT])
    if not quick:
        quick = list(qs.order_by("-hits", "order")[:QUICK_LIMIT])
    return [{"id": f.pk, "question": f.question} for f in quick]


@require_GET
@never_cache
def start(request):
    return JsonResponse({"greeting": GREETING, "quick": _quick_questions(), "wa": StoreSettings.current().whatsapp_link})


@require_POST
def ask(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    message = str(payload.get("message") or "")[: engine.MAX_MESSAGE]
    faq_id = payload.get("faq")

    active = FaqEntry.objects.filter(is_active=True)
    if faq_id:
        entry = active.filter(pk=faq_id).first() if str(faq_id).isdigit() else None
        if entry is None:
            return JsonResponse({"answer": "Pertanyaan itu sudah tidak tersedia.", "suggestions": []})
        reply = engine.Reply(
            answer=engine.fill_placeholders(entry.answer, StoreSettings.current().whatsapp_display),
            link_url=entry.link_url,
            link_label=entry.link_label or "Buka",
            matched=entry,
        )
        message = entry.question
    else:
        reply = engine.answer(message, active, StoreSettings.current().whatsapp_display)

    if reply.matched is not None:
        FaqEntry.objects.filter(pk=reply.matched.pk).update(hits=F("hits") + 1)
    if message.strip() and reply.intent not in ("empty", "greeting", "thanks"):
        ChatLog.objects.create(
            message=message.strip()[:300],
            matched=reply.matched,
            intent=reply.intent,
        )
    data = reply.as_json()
    data["wa"] = StoreSettings.current().whatsapp_link
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Admin: kelola FAQ
# ---------------------------------------------------------------------------

UNANSWERED_LIMIT = 30


@roleRequired(Role.ADMIN)
def manage_faq(request):
    faqs = list(FaqEntry.objects.all())
    unanswered = (
        ChatLog.objects.filter(matched__isnull=True, intent="")
        .values("message")
        .annotate(total=Count("pk"))
        .order_by("-total", "message")[:UNANSWERED_LIMIT]
    )
    return render(
        request,
        "chatbot/manage_faq.html",
        {
            "faqs": faqs,
            "count_quick": sum(1 for f in faqs if f.is_quick and f.is_active),
            "count_off": sum(1 for f in faqs if not f.is_active),
            "unanswered": list(unanswered),
            "form": FaqForm(initial={"question": request.GET.get("dari", "")}),
            "prefill": request.GET.get("dari", ""),
        },
    )


@roleRequired(Role.ADMIN)
@require_POST
def save_faq(request, pk=None):
    instance = get_object_or_404(FaqEntry, pk=pk) if pk else None
    form = FaqForm(request.POST, instance=instance)
    if form.is_valid():
        faq = form.save()
        messages.success(request, f"FAQ “{faq.question}” {'diperbarui' if instance else 'ditambahkan'}.")
    else:
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            for error in errors:
                messages.error(request, f"{label}: {error}" if label else error)
    return redirect("chatbot:manage_faq")


@roleRequired(Role.ADMIN)
@require_POST
def delete_faq(request, pk):
    faq = get_object_or_404(FaqEntry, pk=pk)
    faq.delete()
    messages.success(request, f"FAQ “{faq.question}” dihapus.")
    return redirect("chatbot:manage_faq")


@roleRequired(Role.ADMIN)
@require_POST
def clear_unanswered(request):
    ChatLog.objects.filter(matched__isnull=True, intent="").delete()
    messages.success(request, _("Daftar pertanyaan belum terjawab dibersihkan."))
    return redirect("chatbot:manage_faq")
