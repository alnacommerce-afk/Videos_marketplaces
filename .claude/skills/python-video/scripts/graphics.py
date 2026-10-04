"""Motion graphics: fontes, componentes gráficos reutilizáveis e animações de texto.

Todos os componentes devolvem um `Layer`: uma ou mais superfícies RGBA já desenhadas na posição
final + a animação de entrada. O renderer só chama `layer.draw(frame, t)`.
"""
from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from camera import ease_in_out, ease_out_back, ease_out_cubic

# ----------------------------------------------------------------------------
# Fontes
# ----------------------------------------------------------------------------
_FONT_INDEXES: dict[tuple, dict[str, str]] = {}
_BOLD_FILES = {"Segoe UI": ["segoeuib.ttf"], "Arial": ["arialbd.ttf"], "Calibri": ["calibrib.ttf"],
               "Liberation Sans": ["liberationsans-bold.ttf"], "DejaVu Sans": ["dejavusans-bold.ttf"], "Roboto": ["roboto-bold.ttf"]}
_BAD = ("italic", "oblique", "light", "thin", "hairline", "extralight", "condensed", "narrow", "mono", "serif", "symbol")


def _index_fonts(dirs: list[Path]) -> dict[str, str]:
    idx: dict[str, str] = {}
    for d in dirs:
        d = Path(os.path.expanduser(str(d)))
        if not d.exists():
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith((".ttf", ".otf")):
                    idx.setdefault(fn.lower(), str(Path(root) / fn))
    return idx


def find_font(cfg: dict, fonts_dir: Path, bold: bool = True) -> tuple[str, str]:
    """Escolhe a primeira família disponível da lista de prioridade. Retorna (caminho, família)."""
    dirs = [Path(fonts_dir)] + [Path(p) for p in cfg["fonts"]["system_dirs"]]
    key = tuple(str(d) for d in dirs)
    if key not in _FONT_INDEXES:
        _FONT_INDEXES[key] = _index_fonts(dirs)
    _FONT_INDEX = _FONT_INDEXES[key]
    for family in cfg["fonts"]["priority"]:
        if bold:  # nomes de arquivo "negrito" que não contêm a palavra bold (ex.: segoeuib.ttf)
            for alt in _BOLD_FILES.get(family, []):
                if alt in _FONT_INDEX:
                    return _FONT_INDEX[alt], family
        key = re.sub(r"[\s-]", "", family.lower())
        cands = []
        for fn, path in _FONT_INDEX.items():
            stem = re.sub(r"[\s_-]", "", fn.rsplit(".", 1)[0])
            if not stem.startswith(key):
                continue
            if any(b in stem for b in _BAD):
                continue
            weight = ("extrabold" in stem) * 2 + ("bold" in stem and "semibold" not in stem) * 3 + ("semibold" in stem) * 2 \
                + ("black" in stem) * 1 + ("[" in fn or "wght" in stem) * 3
            regular = ("regular" in stem or stem == key) * 2
            cands.append(((weight if bold else regular), len(stem), path))
        if cands:
            cands.sort(key=lambda c: (-c[0], c[1]))
            return cands[0][2], family
        # nomes de arquivo típicos do Windows/Linux
        for alt in ({"Segoe UI": ["segoeuib.ttf"], "Arial": ["arialbd.ttf"], "Liberation Sans": ["liberationsans-bold.ttf"],
                     "DejaVu Sans": ["dejavusans-bold.ttf"]}.get(family, []) if bold else []):
            if alt in _FONT_INDEX:
                return _FONT_INDEX[alt], family
    raise RuntimeError("Nenhuma fonte encontrada. Coloque um .ttf (ex.: Inter ou Montserrat) em fonts/.")


@functools.lru_cache(maxsize=64)
def get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(path, size)
    if "[" in os.path.basename(path):  # fonte variável: pede o peso Bold
        try:
            f.set_variation_by_name("Bold")
        except Exception:
            pass
    return f


# ----------------------------------------------------------------------------
# Camada animada
# ----------------------------------------------------------------------------
@dataclass
class Layer:
    surf: Image.Image                       # RGBA já com tudo desenhado (fundo + texto)
    x: int
    y: int
    anim: str = "fade"
    t_in: float = 0.2
    dur_in: float = 0.45
    role: str = ""
    text: str = ""
    text_rgb: tuple = (255, 255, 255)
    card_rgba: tuple | None = None          # cor do cartão (para cálculo de contraste)
    font_px: int = 0
    words: list = field(default_factory=list)   # [(surf, x, y)] relativos ao layer, p/ animações por palavra
    bg: Image.Image | None = None           # fundo do cartão separado das palavras
    tracking: dict | None = None            # {font, text, fill} para animação de espaçamento
    slide: str = "left"

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.surf.width, self.surf.height)

    def alpha_surf(self, a: float, surf: Image.Image | None = None) -> Image.Image:
        s = surf or self.surf
        if a >= 0.999:
            return s
        r, g, b, al = s.split()
        return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * max(a, 0.0)))))

    def draw(self, frame: Image.Image, t: float) -> None:
        u = (t - self.t_in) / self.dur_in
        if u <= 0:
            return
        u = min(u, 1.0)
        e = ease_out_cubic(u)
        W, H = frame.size
        a = self.anim
        if a in ("words", "staggered", "kinetic") and self.words:
            if self.bg is not None:
                frame.paste(self.alpha_surf(min(1.0, u * 2), self.bg), (self.x, self.y), self.alpha_surf(min(1.0, u * 2), self.bg))
            step = 0.13 if a == "kinetic" else 0.09
            for i, (ws, wx, wy) in enumerate(self.words):
                wu = (t - self.t_in - i * step) / (0.32 if a != "kinetic" else 0.28)
                if wu <= 0:
                    continue
                wu = min(wu, 1.0)
                if a == "kinetic":
                    sc = 0.55 + 0.45 * ease_out_back(wu, 2.2)
                    w2, h2 = max(1, int(ws.width * sc)), max(1, int(ws.height * sc))
                    img = ws.resize((w2, h2), Image.BICUBIC)
                    px = self.x + wx + (ws.width - w2) // 2
                    py = self.y + wy + (ws.height - h2) // 2
                else:
                    img = ws
                    px, py = self.x + wx, self.y + wy + int((1 - ease_out_cubic(wu)) * 28)
                img = self.alpha_surf(min(1.0, wu * 2.2), img)
                frame.paste(img, (px, py), img)
            return
        if a == "tracking" and self.tracking:
            steps = 10
            q = round((1 - e) * steps)
            img = _render_tracked(self.tracking, q * 3)
            img = self.alpha_surf(min(1.0, u * 2.5), img)
            frame.paste(img, (self.x - (img.width - self.surf.width) // 2, self.y), img)
            return
        surf, x, y, al = self.surf, self.x, self.y, 1.0
        if a == "fade":
            al = e
        elif a == "slide":
            if self.slide == "up":
                y += int((1 - e) * 90)
            else:
                x -= int((1 - e) * 140)
            al = min(1.0, u * 2.2)
        elif a == "scale":
            sc = 0.78 + 0.22 * ease_out_back(u, 1.6)
            w2, h2 = max(1, int(surf.width * sc)), max(1, int(surf.height * sc))
            surf = surf.resize((w2, h2), Image.BICUBIC)
            x += (self.surf.width - w2) // 2
            y += (self.surf.height - h2) // 2
            al = min(1.0, u * 3)
        elif a == "mask":
            w2 = max(1, int(surf.width * ease_in_out(u)))
            surf = surf.crop((0, 0, w2, surf.height))
            al = 1.0
        s2 = self.alpha_surf(al, surf)
        frame.paste(s2, (x, y), s2)


def _render_tracked(tr: dict, extra: int) -> Image.Image:
    font, text, fill = tr["font"], tr["text"], tr["fill"]
    pad = 30
    widths = [font.getlength(ch) for ch in text]
    total = int(sum(widths) + extra * (len(text) - 1)) + pad * 2
    h = font.size + pad * 2
    im = Image.new("RGBA", (total + 2, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    for ch, w in zip(text, widths):
        d.text((x + 3, pad + 4), ch, font=font, fill=(0, 0, 0, 120))
        d.text((x, pad), ch, font=font, fill=fill)
        x += w + extra
    return im


# ----------------------------------------------------------------------------
# Texto com quebra + sombra
# ----------------------------------------------------------------------------
def wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, font_path: str, max_w: int, max_lines: int, start: int, min_px: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Maior fonte (de `start` até `min_px`) em que o texto cabe em `max_lines` linhas dentro de `max_w`.
    `_text_surface` soma ~12 px de folga (sombra), por isso o limite útil é max_w - 14."""
    limit = max_w - 14
    size = start
    while size >= min_px:
        f = get_font(font_path, size)
        lines = wrap_lines(text, f, limit)
        if len(lines) <= max_lines and all(f.getlength(l) <= limit for l in lines):
            return f, lines
        size -= 4
    f = get_font(font_path, min_px)
    return f, wrap_lines(text, f, limit)


def _text_surface(lines, font, fill, shadow=True, align="left", line_gap=1.18, pad=(0, 0)):
    lh = int(font.size * line_gap)
    w = int(max(font.getlength(l) for l in lines)) + 2 * pad[0] + 12
    h = lh * len(lines) + 2 * pad[1] + 12
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        lw = font.getlength(l)
        x = pad[0] + 4 + ({"left": 0, "center": (w - 2 * pad[0] - 12 - lw) / 2, "right": w - 2 * pad[0] - 12 - lw}[align])
        y = pad[1] + 2 + i * lh
        if shadow:
            sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).text((x + 3, y + 5), l, font=font, fill=(0, 0, 0, 150))
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(4)))
            d = ImageDraw.Draw(im)
        d.text((x, y), l, font=font, fill=fill)
    return im


def _place(position: str, w: int, h: int, W: int, H: int, safe: dict, align: str, extra_up: int = 0) -> tuple[int, int]:
    if position == "top":
        y = safe["top"] + 20
    elif position == "center":
        y = (H - h) // 2
    else:
        y = H - safe["bottom"] - h - 24 - extra_up
    if align == "center":
        x = safe["left"] + ((W - safe["left"] - safe["right"]) - w) // 2
    else:
        x = safe["left"]
    return x, y


def _safe_w(W: int, safe: dict, margin: int = 0) -> int:
    return W - safe["left"] - safe["right"] - margin


# ----------------------------------------------------------------------------
# Componentes
# ----------------------------------------------------------------------------
def gradient_overlay(W: int, H: int, bottom: float = 0.55, top: float = 0.30, dim: float = 0.0,
                     vignette: float = 0.2) -> Image.Image:
    """Retorna imagem RGB 'multiplicadora' (255 = sem escurecer) para ImageChops.multiply."""
    import numpy as np
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    g_bot = np.clip((yy - 0.52) / 0.48, 0, 1) ** 1.6 * bottom
    g_top = np.clip((0.30 - yy) / 0.30, 0, 1) ** 1.6 * top
    vig = (((xx - 0.5) ** 2 + (yy - 0.5) ** 2) ** 0.5 / 0.7071) ** 2.2 * vignette
    dark = np.clip(1.0 - g_bot - g_top - vig - dim, 0.0, 1.0)
    arr = (dark * 255).astype("uint8")
    return Image.fromarray(np.repeat(arr[:, :, None], 3, axis=2), "RGB")


def text_card(text, ctx, position="top", size=104, max_lines=3, align="center", anim="scale", role="headline", t_in=0.15):
    W, H, safe, font_path, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    max_w = _safe_w(W, safe, 64)  # sobra espaço para a placa de contraste (2 x 30 px)
    font, lines = fit_text(text.upper() if role == "headline" and len(text) <= 28 else text, font_path, max_w, max_lines, size, 56)
    surf = _text_surface(lines, font, tuple(st["text"]) + (255,), align=align)
    x, y = _place(position, surf.width, surf.height, W, H, safe, align)
    tr = {"font": font, "text": lines[0], "fill": tuple(st["text"]) + (255,)} if len(lines) == 1 else None
    words = _word_surfaces(lines, font, tuple(st["text"]) + (255,), surf.width, align)
    return Layer(surf, x, y, anim if (anim != "tracking" or tr) else "fade", t_in, role=role, text=text,
                 text_rgb=tuple(st["text"]), font_px=font.size, words=words, tracking=tr)


def _word_surfaces(lines, font, fill, total_w, align):
    out, lh = [], int(font.size * 1.18)
    for i, l in enumerate(lines):
        lw = font.getlength(l)
        x0 = {"left": 0, "center": (total_w - 12 - lw) / 2, "right": total_w - 12 - lw}[align] + 4
        pos = x0
        for w in l.split(" "):
            ww = font.getlength(w)
            s = _text_surface([w], font, fill)
            out.append((s, int(pos) - 0, i * lh))
            pos += ww + font.getlength(" ")
    return out


def lower_third(text, ctx, anim="slide", t_in=0.25, role="fact", position="bottom", extra_up=260):
    """Barra de destaque lateral + texto sobre cartão translúcido."""
    W, H, safe, fp, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    pad_x, pad_y, bar = 34, 26, 12
    font, lines = fit_text(text, fp, _safe_w(W, safe, 2 * pad_x + bar), 2, 62, 46)
    ts = _text_surface(lines, font, tuple(st["card_text"]) + (255,), shadow=False)
    w, h = ts.width + 2 * pad_x + bar, ts.height + 2 * pad_y
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(surf)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=26, fill=tuple(st["card"]))
    d.rounded_rectangle((0, 0, bar + 14, h - 1), radius=26, fill=tuple(st["accent"]) + (255,))
    d.rectangle((bar, 0, bar + 14, h - 1), fill=tuple(st["card"]))
    surf.alpha_composite(ts, (pad_x + bar, pad_y))
    x, y = _place(position, w, h, W, H, safe, "left", extra_up)
    return Layer(surf, x, y, anim, t_in, role=role, text=text, text_rgb=tuple(st["card_text"]), card_rgba=tuple(st["card"]),
                 font_px=font.size, slide="left")


def feature_card(text, label, ctx, anim="slide", t_in=0.25, role="card", position="bottom", extra_up=200, check=False):
    """Cartão com etiqueta (chip) do tipo de informação + texto. `check=True` => benefit card com marca ✓."""
    W, H, safe, fp, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    pad, chip_h = 38, 54
    inner_w = _safe_w(W, safe, 2 * pad)
    font, lines = fit_text(text, fp, inner_w - (70 if check else 0), 3, 66, 46)
    ts = _text_surface(lines, font, tuple(st["card_text"]) + (255,), shadow=False)
    lf = get_font(fp, 30)
    chip_w = int(lf.getlength(label.upper())) + 44 if label else 0
    w = max(ts.width + (70 if check else 0), chip_w) + 2 * pad
    h = ts.height + 2 * pad + (chip_h // 2 + 12 if label else 0)
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(surf)
    top = chip_h // 2 if label else 0
    d.rounded_rectangle((0, top, w - 1, h - 1), radius=34, fill=tuple(st["card"]))
    if label:
        d.rounded_rectangle((pad, 0, pad + chip_w, chip_h), radius=chip_h // 2, fill=tuple(st["accent"]) + (255,))
        d.text((pad + 22, 8), label.upper(), font=lf, fill=(20, 20, 24, 255))
    tx = pad + (70 if check else 0)
    if check:
        cy = top + pad + int(font.size * 0.6)
        d.ellipse((pad, cy - 26, pad + 52, cy + 26), fill=tuple(st["accent"]) + (255,))
        d.line((pad + 13, cy, pad + 23, cy + 11, pad + 40, cy - 12), fill=(20, 20, 24, 255), width=7, joint="curve")
    surf.alpha_composite(ts, (tx, top + (chip_h // 2 + 6 if label else 0) + pad - (0 if label else 0)))
    x, y = _place(position, w, h, W, H, safe, "left", extra_up)
    return Layer(surf, x, y, anim, t_in, role=role, text=text, text_rgb=tuple(st["card_text"]), card_rgba=tuple(st["card"]),
                 font_px=font.size, slide="up")


benefit_card = lambda text, label, ctx, **kw: feature_card(text, label, ctx, check=True, **kw)


def product_callout(text, ctx, anim="scale", t_in=0.25, role="fact", position="bottom", extra_up=330):
    """Etiqueta (chip) com ponto de destaque. Fica ancorada na tela, sem apontar para uma parte
    específica do produto (não afirmamos nada sobre onde algo está na foto)."""
    W, H, safe, fp, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    font, lines = fit_text(text, fp, _safe_w(W, safe, 120), 2, 58, 44)
    ts = _text_surface(lines, font, tuple(st["card_text"]) + (255,), shadow=False)
    w, h = ts.width + 110, ts.height + 44
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(surf)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=tuple(st["card"]))
    d.ellipse((30, h // 2 - 12, 54, h // 2 + 12), fill=tuple(st["accent"]) + (255,))
    surf.alpha_composite(ts, (72, 22))
    x, y = _place(position, w, h, W, H, safe, "center", extra_up)
    return Layer(surf, x, y, anim, t_in, role=role, text=text, text_rgb=tuple(st["card_text"]), card_rgba=tuple(st["card"]),
                 font_px=font.size)


def cta_button(text, ctx, anim="scale", t_in=0.35, position="bottom", extra_up=120):
    W, H, safe, fp, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    font, lines = fit_text(text, fp, _safe_w(W, safe, 190), 2, 70, 48)
    ts = _text_surface(lines, font, (20, 20, 24, 255), shadow=False, align="center")
    w, h = ts.width + 150, ts.height + 64
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((30, 40, w + 30, h + 40), radius=h // 2, fill=tuple(st["accent"]) + (110,))
    d = ImageDraw.Draw(surf)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=tuple(st["accent"]) + (255,))
    surf.alpha_composite(ts, (46, 32))
    ax, ay = w - 74, h // 2  # seta desenhada (não depende de glifo da fonte)
    d.polygon([(ax - 14, ay - 22), (ax + 16, ay), (ax - 14, ay + 22), (ax - 6, ay)], fill=(20, 20, 24, 255))
    x, y = _place(position, w, h, W, H, safe, "center", extra_up)
    return Layer(surf, x, y, anim, t_in, role="cta", text=text, text_rgb=(20, 20, 24), card_rgba=tuple(st["accent"]) + (255,),
                 font_px=font.size)


def badge(text, ctx, position="top", anim="fade", t_in=0.2, size=46):
    W, H, safe, fp, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    f = get_font(fp, size)
    w, h = int(f.getlength(text.upper())) + 60, size + 38
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(surf)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=tuple(st["accent"]) + (255,))
    d.text((30, 16), text.upper(), font=f, fill=(20, 20, 24, 255))
    x, y = _place(position, w, h, W, H, safe, "left")
    return Layer(surf, x, y, anim, t_in, role="badge", text=text, text_rgb=(20, 20, 24), card_rgba=tuple(st["accent"]) + (255,), font_px=size)


def label(text, ctx, position="top", anim="fade", t_in=0.2):
    W, H, safe, fp, st = ctx["W"], ctx["H"], ctx["safe"], ctx["font"], ctx["style"]
    f = get_font(fp, 40)
    s = _text_surface([text.upper()], f, tuple(st["text"]) + (255,))
    x, y = _place(position, s.width, s.height, W, H, safe, "left")
    return Layer(s, x, y, anim, t_in, role="label", text=text, text_rgb=tuple(st["text"]), font_px=40)


def highlight_box(w, h, ctx, x, y, anim="mask", t_in=0.3):
    st = ctx["style"]
    surf = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(surf).rounded_rectangle((0, 0, w - 1, h - 1), radius=28, outline=tuple(st["accent"]) + (255,), width=6)
    return Layer(surf, x, y, anim, t_in, role="highlight")


def price_element(price_text, ctx, position="top", anim="scale", t_in=0.3):
    """Só deve ser usado com preço confirmado e brand.show_price=true."""
    return badge(price_text, ctx, position=position, anim=anim, t_in=t_in)


def shape_mask(size: tuple[int, int], radius: int = 0, circle: bool = False) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    if circle:
        d.ellipse((0, 0, size[0] - 1, size[1] - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def luminance(rgb) -> float:
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(rgb1, rgb2) -> float:
    l1, l2 = luminance(rgb1), luminance(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)
