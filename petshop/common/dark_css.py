"""Membuat pasangan mode gelap untuk CSS toko (halaman pelanggan, landing, login).

Setiap file sumber mendapat file ``<nama>-dark.css`` di sebelahnya. Isinya hanya
deklarasi warna dari file sumber, diberi awalan ``html[data-theme="dark"]`` dan
warnanya dipetakan ke palet gelap ungu:

- latar terang (putih, krem, ungu muda, pastel status) menjadi permukaan gelap;
- teks gelap menjadi terang, teks ungu menjadi ungu muda;
- garis tepi terang menjadi garis gelap;
- warna pekat (tombol ungu, hijau WhatsApp, oranye) dibiarkan.

Semua deklarasi warna ikut disalin, termasuk yang warnanya tidak berubah,
supaya urutan dan kekuatan selektor sama persis dengan versi terang.
Jalankan ``python manage.py build_dark_css`` setiap kali CSS sumber berubah;
tes akan gagal kalau file gelap tertinggal.
"""

import colorsys
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SOURCES = [
    "customer/static/customer/css/base.css",
    "customer/static/customer/css/nav.css",
    "customer/static/customer/css/app.css",
    "customer/static/customer/css/home.css",
    "customer/static/customer/css/about.css",
    "customer/static/customer/css/shop.css",
    "customer/static/customer/css/product_card.css",
    "customer/static/customer/css/wishlist.css",
    "customer/static/customer/css/cart.css",
    "customer/static/customer/css/checkout.css",
    "customer/static/customer/css/orders.css",
    "customer/static/customer/css/checkout_ux.css",
    "customer/static/customer/css/track.css",
    "customer/static/customer/css/dashboard.css",
    "customer/static/customer/css/account.css",
    "customer/static/customer/css/my_orders.css",
    "service/static/service/css/site.css",
    "store/static/store/css/notifications.css",
    "store/static/store/css/complaints.css",
    "static/css/camera.css",
    "chatbot/static/chatbot/css/widget.css",
    "account/static/account/css/login.css",
    "static/css/error.css",
]

PREFIX = 'html[data-theme="dark"]'
HEADER = "/* Dibuat otomatis oleh `python manage.py build_dark_css` dari {name}. Jangan diubah manual. */\n"

# Palet gelap (sama dengan mode gelap staf).
PAGE = "#18121f"
CARD = "#211a2b"
SOFT = "#2b2139"
LINE = "#3a2f48"
LINE_STRONG = "#5b4775"
INK = "#f1ebf7"
MUTED = "#b9adc7"
PURPLE_TEXT = "#d8b4fe"

NAMED = {
    "white": (255, 255, 255, 1.0),
    "black": (0, 0, 0, 1.0),
    "transparent": (0, 0, 0, 0.0),
}

COLOR_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(?:white|black|transparent)\b"
)
VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)")

TEXT_PROPS = {"color", "fill", "stroke", "caret-color", "text-decoration-color", "-webkit-text-fill-color"}
BG_PROPS = {"background", "background-color", "background-image", "box-shadow"}
BORDER_PROPS = {
    "border", "border-color", "border-top", "border-right", "border-bottom", "border-left",
    "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
    "border-block", "border-inline", "border-block-start", "border-block-end",
    "border-inline-start", "border-inline-end", "outline", "outline-color",
    "column-rule", "column-rule-color",
}


# ---------- warna ----------

def parse_color(text):
    t = text.strip().lower()
    if t in NAMED:
        return NAMED[t]
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        if len(h) not in (6, 8):
            return None
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (r, g, b, a)
    m = re.match(r"(rgba?|hsla?)\((.*)\)$", t)
    if not m:
        return None
    parts = [p for p in re.split(r"[\s,/]+", m.group(2).strip()) if p]
    if len(parts) < 3:
        return None
    try:
        alpha = 1.0
        if len(parts) > 3:
            alpha = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
        if m.group(1).startswith("rgb"):
            rgb = [float(p[:-1]) * 2.55 if p.endswith("%") else float(p) for p in parts[:3]]
            return (round(rgb[0]), round(rgb[1]), round(rgb[2]), alpha)
        hue = float(parts[0].replace("deg", "")) / 360
        sat = float(parts[1].rstrip("%")) / 100
        lig = float(parts[2].rstrip("%")) / 100
        r, g, b = colorsys.hls_to_rgb(hue % 1, lig, sat)
        return (round(r * 255), round(g * 255), round(b * 255), alpha)
    except ValueError:
        return None


def hsl(c):
    h, light, s = colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)
    return h * 360, s, light


def from_hsl(h, s, light, alpha):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, light, s)
    return fmt((round(r * 255), round(g * 255), round(b * 255), alpha))


def fmt(c):
    r, g, b, a = c
    if a >= 0.999:
        return "#%02x%02x%02x" % (r, g, b)
    return "rgba(%d, %d, %d, %s)" % (r, g, b, ("%.3f" % a).rstrip("0").rstrip("."))


def with_alpha(hex_color, alpha):
    c = parse_color(hex_color)
    return fmt((c[0], c[1], c[2], alpha))


def purpleish(h, s):
    return s < 0.2 or 240 <= h <= 345


def dark_bg(c):
    if c[3] == 0:
        return None
    h, s, light = hsl(c)
    if light >= 0.99:
        return with_alpha(CARD, c[3])
    if light >= 0.955:
        return with_alpha(PAGE, c[3])
    if light >= 0.8:
        return with_alpha(SOFT, c[3]) if purpleish(h, s) else from_hsl(h, min(s, 0.45), 0.17, c[3])
    if light >= 0.6:
        return from_hsl(h, min(s, 0.45), 0.28, c[3])
    return None


def dark_text(c):
    h, s, light = hsl(c)
    if light >= 0.6 or c[3] == 0:
        return None
    if light < 0.22 or (s < 0.25 and light < 0.3):
        return with_alpha(INK, c[3])
    if s < 0.25:
        return with_alpha(MUTED, c[3])
    if 245 <= h <= 320:
        return with_alpha(PURPLE_TEXT, c[3])
    return from_hsl(h, min(s, 0.85), 0.74, c[3])


def dark_border(c):
    if c[3] == 0:
        return None
    h, s, light = hsl(c)
    if light >= 0.8:
        return with_alpha(LINE, c[3]) if purpleish(h, s) else from_hsl(h, min(s, 0.35), 0.28, c[3])
    if light >= 0.6:
        return with_alpha(LINE_STRONG, c[3]) if purpleish(h, s) else from_hsl(h, min(s, 0.4), 0.38, c[3])
    return None


def map_colors(value, mapper):
    def repl(m):
        c = parse_color(m.group(0))
        if c is None:
            return m.group(0)
        out = mapper(c)
        return out if out else m.group(0)
    return COLOR_RE.sub(repl, value)


def is_solid(value):
    """Latar pekat (tombol, lencana) yang tidak dipetakan: teksnya dibiarkan."""
    for m in COLOR_RE.finditer(value):
        c = parse_color(m.group(0))
        if c and c[3] > 0.5 and dark_bg(c) is None:
            return True
    return False


# ---------- pengurai CSS sederhana ----------

def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def parse_blocks(css):
    """Mengembalikan daftar (prelude, isi) bertingkat; isi berupa str atau daftar."""
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        if ";" in prelude and prelude.startswith("@"):
            prelude = prelude.rsplit(";", 1)[-1].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        if prelude.startswith(("@media", "@supports", "@layer", "@container")):
            out.append((prelude, parse_blocks(body)))
        else:
            out.append((prelude, body))
        i = k
    return out


def declarations(body):
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for p in parts:
        if ":" not in p:
            continue
        name, value = p.split(":", 1)
        name = name.strip().lower()
        value = " ".join(value.split())
        if name and value:
            yield name, value


def collect_tokens(blocks, tokens):
    for prelude, body in blocks:
        if isinstance(body, list):
            collect_tokens(body, tokens)
            continue
        for name, value in declarations(body):
            if name.startswith("--"):
                tokens.setdefault(name, value)


def resolve(value, tokens, depth=0):
    if "var(" not in value or depth > 5:
        return value

    def repl(m):
        name, fallback = m.group(1), m.group(2)
        if name in tokens:
            return resolve(tokens[name], tokens, depth + 1)
        if fallback is not None:
            return resolve(fallback.strip(), tokens, depth + 1)
        return m.group(0)

    return resolve(VAR_RE.sub(repl, value), tokens, depth + 1)


def scope(selector):
    sel = selector.strip()
    if sel.startswith(":root"):
        return PREFIX + sel[len(":root"):]
    if re.match(r"html(?![\w-])", sel):
        return PREFIX + sel[4:]
    return PREFIX + " " + sel


def dark_rule(prelude, body, tokens):
    if prelude.startswith("@"):
        return None
    decls = list(declarations(body))
    if any(name == "--keep-in-dark" for name, _ in decls):
        return None  # aturan sengaja sama di mode gelap (mis. latar putih foto produk)
    resolved = {name: resolve(value, tokens) for name, value in decls}
    keep_text = any(name in ("background", "background-color") and is_solid(resolved[name]) for name in resolved)
    out = []
    for name, value in decls:
        if name.startswith("--"):
            continue
        if name in TEXT_PROPS:
            mapper = (lambda c: None) if keep_text else dark_text
        elif name in BG_PROPS:
            mapper = dark_bg
        elif name in BORDER_PROPS:
            mapper = dark_border
        elif name.startswith(("background", "-webkit-background")):
            # background shorthand di aturan gelap mereset clip/size/posisi; salin juga.
            out.append("%s: %s" % (name, value))
            continue
        else:
            continue
        light = resolved[name]
        # Deklarasi tanpa warna (none, 0, inherit) tetap disalin supaya urutan aturan sama.
        out.append("%s: %s" % (name, value if "var(" in light else map_colors(light, mapper)))
    if not out:
        return None
    selectors = ", ".join(scope(s) for s in split_selectors(prelude))
    return "%s { %s; }" % (selectors, "; ".join(out))


def split_selectors(prelude):
    parts, depth, cur = [], 0, ""
    for ch in prelude:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [" ".join(p.split()) for p in parts if p.strip()]


def render(blocks, tokens, indent=""):
    lines = []
    for prelude, body in blocks:
        if isinstance(body, list):
            if prelude.startswith(("@keyframes", "@font-face")):
                continue
            inner = render(body, tokens, indent + "  ")
            if inner:
                lines.append("%s%s {" % (indent, " ".join(prelude.split())))
                lines.extend(inner)
                lines.append(indent + "}")
            continue
        if prelude.startswith(("@keyframes", "@font-face", "@-webkit-keyframes")):
            continue
        rule = dark_rule(prelude, body, tokens)
        if rule:
            lines.append(indent + rule)
    return lines


def dark_path(source):
    path = BASE_DIR / source
    return path.with_name(path.stem + "-dark.css")


def build():
    """Mengembalikan {path file gelap: isi}."""
    parsed = {src: parse_blocks(strip_comments((BASE_DIR / src).read_text(encoding="utf-8"))) for src in SOURCES}
    tokens = {}
    for blocks in parsed.values():
        collect_tokens(blocks, tokens)
    result = {}
    for src, blocks in parsed.items():
        body = "\n".join(render(blocks, tokens))
        result[dark_path(src)] = HEADER.format(name=Path(src).name) + body + "\n"
    return result
