"""Fixtures sintéticas para TESTES. Nada aqui descreve um produto real da ALNA:
as fotos são formas geométricas geradas por código e os 'fatos' são texto de teste."""
from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def make_photo(path: Path, size=(1200, 1200), hue=(220, 90, 60), bg=(244, 241, 236), seed=0) -> Path:
    rnd = random.Random(seed)
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    w, h = size
    for y in range(h):  # gradiente de mesa
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(c * (1 - 0.12 * k)) for c in bg))
    cx, cy = w // 2, int(h * 0.52)
    bw, bh = int(w * 0.52), int(h * 0.58)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((cx - bw // 2, cy + bh // 2 - 30, cx + bw // 2, cy + bh // 2 + 50), fill=(0, 0, 0, 90))
    im.paste(shadow.filter(ImageFilter.GaussianBlur(24)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(24)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2), radius=60, fill=hue)
    for i in range(7):  # listras
        x = cx - bw // 2 + 40 + i * (bw - 80) // 6
        d.rounded_rectangle((x, cy - bh // 2 + 30, x + 18, cy + bh // 2 - 30), radius=9,
                            fill=tuple(min(255, c + 40) for c in hue))
    for _ in range(14):  # pontos de detalhe (dão "textura" para o ponto de interesse)
        x, y = rnd.randint(cx - bw // 2 + 30, cx + bw // 2 - 30), rnd.randint(cy - bh // 2 + 30, cy + bh // 2 - 30)
        d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=92)
    return path


def make_catalog(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    prods = []
    spec = [
        ("teste-001", "PRODUTO TESTE UM", [(210, 70, 80), (60, 110, 200), (40, 150, 120)],
         [{"kind": "dimension", "text": "80 x 150 cm"}, {"kind": "material", "text": "Material de teste A"},
          {"kind": "quantity", "text": "Kit com 2 unidades"}, {"kind": "use", "text": "Ideal para testes de vídeo"}],
         "Descrição de teste. Primeira frase de teste. Segunda frase de teste."),
        ("teste-002", "PRODUTO TESTE DOIS", [(30, 30, 40), (200, 160, 60)],
         [{"kind": "color", "text": "Cor de teste azul"}, {"kind": "characteristic", "text": "Característica de teste B"},
          {"kind": "gift", "text": "Ótima opção para presentear (texto de teste)"}],
         ""),
        ("teste-003", "PRODUTO TESTE TRES", [(120, 160, 90)],
         [], "Medidas: 30 x 40 cm\nMaterial: material de teste C\nGarantia vitalícia contra qualquer defeito\nO melhor do mercado"),
    ]
    for i, (pid, name, hues, facts, desc) in enumerate(spec):
        imgs = []
        for k, hue in enumerate(hues):
            size = [(1200, 1200), (1400, 1000), (1000, 1300)][k % 3]
            imgs.append(str(make_photo(root / "fotos" / f"{pid}-{k + 1}.jpg", size=size, hue=hue, seed=i * 10 + k).relative_to(root)))
        prods.append({"id": pid, "name": name, "category": "teste", "url": f"https://exemplo.invalid/produto/{pid}",
                      "images": imgs, "description": desc, "facts": facts})
    p = root / "catalog.json"
    p.write_text(json.dumps({"products": prods}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
