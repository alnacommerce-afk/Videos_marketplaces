"""Câmera virtual para fotos: pontos de interesse, enquadramentos e movimentos.

Modelo único: a foto tem uma escala base `s0 = fill * W / largura` (a foto cabe na largura do
quadro). O zoom multiplica essa escala. A região visível, em pixels da foto, é
(W/s, H/s) centrada em (cx, cy). Se a região for maior que a foto, o resto é fundo desfocado.
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image

MAX_UPSCALE = 3.2  # acima disso a foto fica mole demais


# ----------------------------------------------------------------------------
# Easing
# ----------------------------------------------------------------------------
def ease_in_out(p: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * min(max(p, 0.0), 1.0))


def ease_out_cubic(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_out_back(p: float, k: float = 1.4) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 + (k + 1) * (p - 1) ** 3 + k * (p - 1) ** 2


def ease_in_cubic(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p ** 3


# ----------------------------------------------------------------------------
# Pontos de interesse (sem IA): energia de bordas com viés para o centro
# ----------------------------------------------------------------------------
def focal_candidates(img: Image.Image, k: int = 4) -> list[dict]:
    """Retorna até k pontos (cx, cy normalizados) onde há mais detalhe, bem espaçados.
    Serve só para escolher ENQUADRAMENTO; nunca para descrever o produto."""
    small = img.convert("L")
    small.thumbnail((200, 200))
    a = np.asarray(small, dtype=np.float32)
    gy, gx = np.gradient(a)
    mag = np.hypot(gx, gy)
    h, w = mag.shape
    # suaviza com integral image (caixa 9x9)
    r = 4
    pad = np.pad(mag, r, mode="edge")
    c = pad.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    box = c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]
    box = box[:h, :w]
    yy, xx = np.mgrid[0:h, 0:w]
    center = 1.0 - 0.6 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) ** 0.5) / 0.7071
    score = box * center
    out = []
    work = score.copy()
    for _ in range(k):
        idx = np.unravel_index(np.argmax(work), work.shape)
        if work[idx] <= 0:
            break
        y, x = idx
        out.append({"cx": round((x + 0.5) / w, 4), "cy": round((y + 0.5) / h, 4), "score": float(work[idx])})
        y0, y1, x0, x1 = max(0, y - h // 4), min(h, y + h // 4), max(0, x - w // 4), min(w, x + w // 4)
        work[y0:y1, x0:x1] = 0
    if not out:
        out = [{"cx": 0.5, "cy": 0.5, "score": 0.0}]
    return out


# ----------------------------------------------------------------------------
# Planejamento de câmera
# ----------------------------------------------------------------------------
SHOTS = {
    # fill: fração da largura do quadro ocupada pela foto no zoom 1; zc: múltiplo do zoom "cover"
    "hero":      {"fill": 0.94, "kind": "z", "z": (1.00, 1.00), "focal": None},
    "hero_wide": {"fill": 0.80, "kind": "z", "z": (1.00, 1.00), "focal": None},
    "detail":    {"fill": 0.94, "kind": "cover", "z": (1.00, 1.15), "focal": 0},
    "detail2":   {"fill": 0.94, "kind": "cover", "z": (1.05, 1.25), "focal": 1},
    "macro":     {"fill": 0.94, "kind": "cover", "z": (1.55, 1.95), "focal": 0},
    "macro2":    {"fill": 0.94, "kind": "cover", "z": (1.55, 1.95), "focal": 1},
}


def base_scale(fill: float, W: int, iw: int) -> float:
    return fill * W / iw


def cover_zoom(fill: float, W: int, H: int, iw: int, ih: int) -> float:
    s0 = base_scale(fill, W, iw)
    return max(W / (s0 * iw), H / (s0 * ih))


def plan_camera(shot: str, move: str, img_size: tuple[int, int], focals: list[dict], W: int, H: int,
                rng: random.Random, start_from: dict | None = None, direction: int | None = None) -> dict:
    """Devolve {fill, z0, z1, c0, c1, ease, parallax, shot, move}. Todos os valores são
    determinísticos dado (rng, entradas) — o storyboard guarda o resultado."""
    spec = SHOTS[shot]
    iw, ih = img_size
    fill = spec["fill"]
    s0 = base_scale(fill, W, iw)
    zmax = max(1.0, MAX_UPSCALE / s0)
    if spec["kind"] == "cover":
        zc = min(cover_zoom(fill, W, H, iw, ih), zmax)
        za, zb = spec["z"][0] * zc, spec["z"][1] * zc
    else:
        za, zb = spec["z"]
    za, zb = min(za, zmax), min(zb, zmax)

    fi = spec["focal"]
    if fi is None:
        cx, cy = 0.5, 0.5
    else:
        f = focals[min(fi, len(focals) - 1)]
        cx, cy = f["cx"], f["cy"]
    c0 = [cx, cy]
    c1 = [cx, cy]
    grow = rng.uniform(1.10, 1.18)
    rnd_dir = rng.choice([-1, 1])
    direction = direction if direction in (-1, 1) else rnd_dir  # sentido herdado da cena anterior (continuidade)
    amp = 0.10

    if move == "push_in":
        z0, z1 = za, min(max(zb, za * grow), zmax)
    elif move == "pull_out":
        z1, z0 = za, min(max(zb, za * grow), zmax)
    elif move == "pan_h":
        z0 = z1 = min(max(za, zb) * 1.04, zmax)
        c0[0] -= direction * amp
        c1[0] += direction * amp
    elif move == "pan_v":
        z0 = z1 = min(max(za, zb) * 1.04, zmax)
        c0[1] -= direction * amp
        c1[1] += direction * amp
    elif move == "diagonal":
        z0, z1 = za, min(za * 1.08, zmax)
        c0 = [cx - direction * amp * 0.8, cy - amp * 0.8]
        c1 = [cx + direction * amp * 0.8, cy + amp * 0.8]
    else:  # "static"
        z0 = z1 = za
    if start_from:  # match cut: continua exatamente de onde a cena anterior terminou
        dz = z1 / z0 if z0 else 1.0
        dc = [c1[0] - c0[0], c1[1] - c0[1]]
        z0 = start_from["z1"]
        z1 = min(z0 * dz, zmax)
        c0 = list(start_from["c1"])
        c1 = [c0[0] + dc[0], c0[1] + dc[1]]
    clamp = lambda v: round(min(max(v, 0.0), 1.0), 4)
    return {"shot": shot, "move": move, "dir": direction, "fill": fill, "z0": round(z0, 4), "z1": round(z1, 4),
            "c0": [clamp(c0[0]), clamp(c0[1])], "c1": [clamp(c1[0]), clamp(c1[1])],
            "ease": "in_out", "parallax": bool(shot.startswith("hero") and rng.random() < 0.5)}


def camera_at(cam: dict, p: float) -> tuple[float, float, float]:
    """Zoom e centro no progresso p (0..1)."""
    e = ease_in_out(p) if cam.get("ease") == "in_out" else min(max(p, 0.0), 1.0)
    z = cam["z0"] + (cam["z1"] - cam["z0"]) * e
    cx = cam["c0"][0] + (cam["c1"][0] - cam["c0"][0]) * e
    cy = cam["c0"][1] + (cam["c1"][1] - cam["c0"][1]) * e
    return z, cx, cy


def view_box(cam: dict, p: float, img_size: tuple[int, int], W: int, H: int) -> dict:
    """Região da foto visível e onde ela cai na tela.

    Retorna src box (float) e dest rect (int). Se a região for maior que a foto, a foto fica
    centralizada e o fundo desfocado aparece no entorno."""
    iw, ih = img_size
    z, cx, cy = camera_at(cam, p)
    s = base_scale(cam["fill"], W, iw) * z
    vw, vh = W / s, H / s
    x0 = cx * iw - vw / 2
    y0 = cy * ih - vh / 2
    if vw <= iw:
        x0 = min(max(x0, 0), iw - vw)
    else:
        x0 = (iw - vw) / 2
    if vh <= ih:
        y0 = min(max(y0, 0), ih - vh)
    else:
        y0 = (ih - vh) / 2 + (cy - 0.5) * (ih - vh) * 0.0
    ix0, iy0 = max(x0, 0.0), max(y0, 0.0)
    ix1, iy1 = min(x0 + vw, iw), min(y0 + vh, ih)
    dx, dy = round((ix0 - x0) * s), round((iy0 - y0) * s)
    dw, dh = max(1, round((ix1 - ix0) * s)), max(1, round((iy1 - iy0) * s))
    return {"src": (ix0, iy0, ix1, iy1), "dest": (dx, dy, dw, dh), "scale": s, "z": z}
