"""Kit de tipografia: vários modelos de caixa, fonte, cor e efeito, escolhidos conforme o MOMENTO do vídeo.

Cada variante é uma combinação (fonte, caixa, cor, contorno, destaque de palavra, animação). A escolha depende da
transição que entra na cena (corte seco, dissolve, whip...) e nunca repete a variante da cena anterior, para o texto
acompanhar o ritmo: transição enérgica -> contorno/marcador/cinético; dissolve -> itálico serifado/elegante.

O texto exibido continua rastreável (vem de fato confirmado/nome); o kit só decide COMO ele aparece.
Fontes: procura no fonts/ da skill e nas pastas do sistema (Windows: Georgia, Arial Black, Impact, Segoe UI, Consolas...).
Sem a fonte especial, cai na fonte principal e simula o itálico por inclinação.
"""
from __future__ import annotations

import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import graphics as g

ACCENT = (255, 205, 0)
CORAL = (255, 94, 91)
MINT = (60, 220, 170)
WHITE = (255, 255, 255)
INK = (20, 20, 24)

# nomes de arquivo (minúsculos) por papel tipográfico, em ordem de preferência
FONT_FILES = {
    "sans_italic": ["segoeuiz.ttf", "arialbi.ttf", "liberationsans-bolditalic.ttf", "freesansboldoblique.ttf", "dejavusans-boldoblique.ttf"],
    "serif_italic": ["georgiaz.ttf", "georgiai.ttf", "timesbi.ttf", "liberationserif-bolditalic.ttf", "freeserifbolditalic.ttf"],
    "black": ["ariblk.ttf", "impact.ttf", "segoeuib.ttf"],
    "mono": ["consolab.ttf", "courbd.ttf", "dejavusansmono-bold.ttf", "freemonobold.ttf"],
}

# fonte, caixa, cores, contorno, destaque da palavra-chave, animação
VARIANTS = {
    "marker":        dict(font="sans_bold", case="upper", box=dict(rgb=ACCENT), fill=INK, emph=None, anim="slide"),
    "serif_italic":  dict(font="serif_italic", case="none", box=None, fill=WHITE, emph=dict(kind="color", rgb=ACCENT), anim="words"),
    "outline_black": dict(font="black", case="upper", box=None, fill=WHITE, stroke=(7, (0, 0, 0)), emph=dict(kind="color", rgb=ACCENT), anim="kinetic"),
    "tape":          dict(font="sans_bold", case="none", box=dict(rgb=WHITE), fill=INK, emph=dict(kind="box", rgb=CORAL, fill=WHITE), anim="scale", tilt=-2.5),
    "mono_tag":      dict(font="mono", case="upper", box=dict(rgb=(14, 14, 18)), fill=ACCENT, emph=None, anim="slide"),
    "italic_pop":    dict(font="sans_italic", case="none", box=None, fill=WHITE, emph=dict(kind="box", rgb=MINT, fill=INK), anim="words"),
    "strike_note":   dict(font="sans_bold", case="none", box=dict(rgb=(14, 14, 18)), fill=WHITE, emph=dict(kind="strike", rgb=CORAL), anim="fade"),
}
CLASSIC = ("classic_bar", "classic_chip")  # os componentes antigos (barra lateral e etiqueta) também entram na rotação do texto de fato

MOMENT = {  # transição que ENTRA na cena -> variantes que combinam com o ritmo
    "whip": ["outline_black", "marker", "italic_pop"],
    "directional_wipe": ["outline_black", "marker", "mono_tag"],
    "zoom": ["tape", "outline_black", "marker"],
    "dissolve": ["serif_italic", "italic_pop", "tape"],
    "match_cut": ["serif_italic", "tape"],
    "hard_cut": ["marker", "mono_tag", "tape", "outline_black"],
}
CLOSING_PREF = ["serif_italic", "outline_black", "tape"]
# strike_note (texto riscado) NÃO entra sozinho na rotação: só com um "antes" real. Pode ser pedido por um beat.


def pick_variant(role: str, transition: str | None, prev: str | None, rng: random.Random) -> str:
    if role == "closing":
        pool = list(CLOSING_PREF)
    else:
        pool = list(MOMENT.get(transition or "hard_cut", MOMENT["hard_cut"]))
        if role == "fact":
            pool += list(CLASSIC)
    pool = [v for v in pool if v != prev] or pool
    return rng.choice(pool)


_KIT_CACHE: dict = {}


def kit_fonts(cfg: dict, fonts_dir: Path, main_font: str) -> dict[str, tuple[str, bool]]:
    """papel -> (arquivo, simular_itálico). `sans_bold` é a fonte principal."""
    dirs = [Path(fonts_dir)] + [Path(p) for p in cfg["fonts"]["system_dirs"]]
    key = tuple(str(d) for d in dirs) + (main_font,)
    if key in _KIT_CACHE:
        return _KIT_CACHE[key]
    idx = g._FONT_INDEXES.get(tuple(str(d) for d in dirs)) or g._index_fonts(dirs)
    out = {"sans_bold": (main_font, False)}
    for role, names in FONT_FILES.items():
        hit = next((idx[n] for n in names if n in idx), None)
        out[role] = (hit, False) if hit else (main_font, role.endswith("italic"))
    _KIT_CACHE[key] = out
    return out


def key_word_index(words: list[str]) -> int:
    """Palavra que merece destaque: a que tem número/medida; senão a mais longa (>= 5 letras); senão a última."""
    for i, w in enumerate(words):
        if re.search(r"\d", w):
            return i
    best = max(range(len(words)), key=lambda i: len(re.sub(r"\W", "", words[i])))
    return best if len(re.sub(r"\W", "", words[best])) >= 5 else len(words) - 1


def _shear(im: Image.Image, k: float = 0.22) -> Image.Image:
    w, h = im.size
    pad = int(h * k)
    return im.transform((w + pad, h), Image.AFFINE, (1, k, -pad, 0, 1, 0), Image.BICUBIC)


def _word_surface(word, font, fill, stroke, slant, emph, fonts, size):
    """Superfície RGBA de uma palavra (com destaque, se for a palavra-chave)."""
    kind = emph["kind"] if emph else None
    if kind == "box" and emph.get("fill"):
        fill = emph["fill"]
    elif kind == "color":
        fill = emph["rgb"]
    pad = 10 + (stroke[0] if stroke else 0)
    w = int(font.getlength(word)) + 2 * pad + (10 if slant else 0)
    h = int(size * 1.25) + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == "box":
        d.rounded_rectangle((0, 4, w - 1, h - 4), radius=int(size * 0.28), fill=tuple(emph["rgb"]) + (255,))
    if stroke:
        d.text((pad, pad), word, font=font, fill=tuple(fill) + (255,), stroke_width=stroke[0], stroke_fill=tuple(stroke[1]) + (255,))
    else:
        d.text((pad, pad), word, font=font, fill=tuple(fill) + (255,))
    if kind == "strike":
        y = pad + int(size * 0.62)
        d.line((pad - 2, y, w - pad + 2, y), fill=tuple(emph["rgb"]) + (255,), width=max(6, size // 11))
    if kind == "underline":
        y = pad + int(size * 1.12)
        d.line((pad, y, w - pad, y), fill=tuple(emph["rgb"]) + (255,), width=max(6, size // 12))
    if slant:
        im = _shear(im)
    return im


def styled_layer(text: str, variant: str, role: str, ctx: dict, fonts: dict, position: str = "bottom", size: int = 88,
                 max_lines: int = 3, t_in: float = 0.25, anim: str | None = None, extra_up: int = 120) -> g.Layer:
    """Desenha `text` no estilo `variant`. Quebra em linhas dentro da safe area."""
    spec = VARIANTS[variant]
    W, H, safe = ctx["W"], ctx["H"], ctx["safe"]
    box = spec.get("box")
    box_pad = (36, 26) if box else (0, 0)
    max_w = g._safe_w(W, safe, 64) - 2 * box_pad[0]
    t = text.upper() if spec["case"] == "upper" else text
    words = t.split()
    path, slant_main = fonts[spec["font"]]
    emph_spec = spec.get("emph")
    ki = key_word_index(words) if emph_spec and len(words) > 1 else (0 if emph_spec else -1)
    stroke = spec.get("stroke")
    for px in range(size, 51, -4):
        font = g.get_font(path, px)
        lines, cur, cur_w = [], [], 0
        sp = font.getlength(" ")
        surfs = []
        for i, w in enumerate(words):
            ws = _word_surface(w, font, spec["fill"], stroke, slant_main, emph_spec if i == ki else None, fonts, px)
            surfs.append(ws)
            if cur and cur_w + sp + ws.width > max_w:
                lines.append(cur)
                cur, cur_w = [], 0
            cur_w += (sp if cur else 0) + ws.width
            cur.append(i)
        lines.append(cur)
        if len(lines) <= max_lines and all(sum(surfs[i].width for i in ln) + sp * (len(ln) - 1) <= max_w for ln in lines):
            break
    lh = int(px * 1.2)
    widths = [int(sum(surfs[i].width for i in ln) + sp * (len(ln) - 1)) for ln in lines]
    tw, th = max(widths), lh * len(lines) + int(px * 0.15)
    sw, sh = tw + 2 * box_pad[0], th + 2 * box_pad[1]
    surf = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    bg = None
    if box:
        bg = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(bg).rounded_rectangle((0, 0, sw - 1, sh - 1), radius=30, fill=tuple(box["rgb"]) + (240,))
        surf.alpha_composite(bg)
    else:  # sem caixa: sombra suave para destacar do fundo
        sh_im = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    word_pos = []
    for li, ln in enumerate(lines):
        x = box_pad[0] + (tw - widths[li]) // 2
        y = box_pad[1] + li * lh - int(px * 0.1)
        for i in ln:
            word_pos.append((surfs[i], int(x), int(y)))
            x += surfs[i].width + sp
    if not box:
        shadow = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        for ws, x, y in word_pos:
            a = ws.split()[3].point(lambda v: int(v * 0.55))
            shadow.paste((0, 0, 0, 255), (x + 3, y + 6), a)
        surf.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(5)))
    for ws, x, y in word_pos:
        surf.alpha_composite(ws, (x, y))
    a = anim or spec["anim"]
    tilt = spec.get("tilt")
    layer_words = word_pos
    if tilt:
        surf = surf.rotate(tilt, expand=True, resample=Image.BICUBIC)
        bg, layer_words = None, []
        if a in ("words", "kinetic", "staggered"):
            a = "scale"
    elif a in ("words", "kinetic", "staggered"):
        layer_words = word_pos
    x, y = g._place(position, surf.width, surf.height, W, H, safe, "center", extra_up)
    card = tuple(box["rgb"]) + (240,) if box else None
    return g.Layer(surf, x, y, a, t_in, role=role, text=text, text_rgb=tuple(spec["fill"]), card_rgba=card,
                   font_px=px, words=layer_words, bg=bg if a in ("words", "kinetic", "staggered") else None, slide="left")
