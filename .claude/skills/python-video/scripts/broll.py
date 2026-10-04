"""B-roll de AMBIENTE (Pixabay): cortes curtos que ilustram um USO que a loja já confirma.

Regras (todas verificadas no quality gate):
  * o tema da busca vem SÓ de palavras de fatos confirmados do tipo `use` ("Ideal para praia, piscina...");
  * o clipe NUNCA ilustra material, medida ou característica; a cena mostra o texto literal do fato de uso;
  * a cena leva o rótulo "Imagem ilustrativa";
  * clipes cujas tags batem com o próprio produto (ex.: 'towel' para uma toalha) são descartados, porque
    mostrariam OUTRO produto; clipes com crianças são evitados;
  * origem (id, autor, link) fica registrada em creditos.txt e no relatório do vídeo.

Chave: variável de ambiente PIXABAY_API_KEY ou o arquivo local `APIpixabay` (fora do git). Nunca vai para o repositório.
A API exige cache de 24 h e proíbe download em massa: buscamos só o que vamos usar e guardamos cada clipe.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

from common import Logger, PipelineError, cache_dir, iso, ffprobe_json, sha256_file
from localsecrets import PIXABAY_KEY, read_secret

# tema -> (regex em pt, consulta pt, consulta en). Só estes temas geram busca.
THEMES = [
    ("praia", r"\bpraia\b", "praia", "beach"),
    ("piscina", r"\bpiscina\b", "piscina", "swimming pool"),
    ("academia", r"\bacademia\b|\btreino\b|\bmusculação\b", "academia", "gym workout"),
    ("viagem", r"\bviage(m|ns)\b", "viagem", "travel"),
    ("caminhada", r"\bcaminhada\b", "caminhada", "walking nature"),
    ("danca", r"\bdan[cç]a\b", "dança", "dance"),
    ("cozinha", r"\bcozinha\b|\bcozinhar\b", "cozinha", "kitchen cooking"),
    ("banho", r"\bbanho\b", "banheiro", "bathroom"),
    ("yoga", r"\byoga\b|\bpilates\b", "yoga", "yoga"),
    ("camping", r"\bcamping\b|\bacampamento\b", "camping", "camping"),
    ("jardim", r"\bjardim\b", "jardim", "garden"),
]

# palavras do produto -> equivalentes em inglês, para descartar clipes que mostrem OUTRO produto igual
PRODUCT_WORDS_EN = {"toalha": ["towel"], "tabua": ["cutting board", "board"], "colher": ["spoon"], "rolo": ["rolling pin"],
                    "top": ["top", "crop"], "madeira": ["wood", "wooden"], "faca": ["knife"], "panela": ["pot", "pan"],
                    "camiseta": ["shirt"], "legging": ["legging"], "bolsa": ["bag"], "copo": ["cup", "glass"]}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def themes_for(brief: dict) -> list[dict]:
    """Temas permitidos, cada um ligado ao fato de USO que o justifica (rastreabilidade)."""
    out, seen = [], set()
    for f in brief["confirmed_facts"]:
        if not f["usable"] or f["kind"] != "use":
            continue
        for theme, pat, q_pt, q_en in THEMES:
            if theme not in seen and re.search(pat, f["text"], re.I):
                seen.add(theme)
                out.append({"theme": theme, "fact_id": f["id"], "queries": [("pt", q_pt), ("en", q_en)]})
    return out


def conflict_words(brief: dict) -> set[str]:
    """Palavras que, se aparecerem nas tags do clipe, indicam que ele mostra o MESMO tipo de produto (outro produto)."""
    words = set()
    text = _norm(brief["product"]["name"] + " " + brief["product"].get("category", ""))
    for pt, ens in PRODUCT_WORDS_EN.items():
        if re.search(rf"\b{pt}", text):
            words.update([pt] + ens)
    for tok in re.findall(r"[a-z]{5,}", text):
        words.add(tok)
    return words


def choose_hit(hits: list[dict], conflicts: set[str], cfg: dict, skip_ids: set | frozenset = frozenset()) -> dict | None:
    """Primeiro hit que passa nos filtros (a API já devolve por popularidade)."""
    b = cfg["broll"]
    avoid = {t.lower() for t in b["avoid_tags"]}
    for h in hits:
        if h.get("id") in skip_ids:
            continue
        tags = {t.strip().lower() for t in (h.get("tags") or "").split(",")}
        tag_text = " ".join(tags)
        dur = h.get("duration") or 0
        vids = h.get("videos") or {}
        big = vids.get("large") or {}
        med = vids.get("medium") or {}
        rend = big if big.get("url") else med
        # "min_width" vale para o lado MAIOR: um clipe vertical 1080x1920 é ótimo para 9:16 e não pode ser descartado
        if not rend.get("url") or max(rend.get("width", 0), rend.get("height", 0)) < b["min_width"]:
            continue
        if not (b["min_clip_s"] <= dur <= b["max_clip_s"]):
            continue
        if tags & avoid or any(a in tag_text for a in avoid):
            continue
        if any(re.search(rf"\b{re.escape(w)}", tag_text) for w in conflicts):
            continue
        return {"hit": h, "rendition": {"url": rend["url"], "width": rend["width"], "height": rend["height"],
                                         "size": rend.get("size", 0), "name": "large" if rend is big else "medium"}}
    return None


def search_pixabay(http, key: str, query: str, lang: str, cfg: dict) -> list[dict]:
    b = cfg["broll"]
    data = http.get_json(b["api_url"], {"key": key, "q": query, "lang": lang, "per_page": str(b["per_page"]),
                                        "safesearch": "true", "order": "popular", "min_width": "1000"},  # a API filtra pela largura: 1000 inclui os verticais
                         ttl_hours=b["cache_ttl_hours"])  # a API exige cache de 24 h
    return data.get("hits", []) if isinstance(data, dict) else []


def download_clip(http, rend: dict, dest: Path, logger: Logger) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    http.download(rend["url"], dest, max_mb=300)
    info = ffprobe_json(dest)  # arquivo precisa abrir de verdade
    if not any(s["codec_type"] == "video" for s in info["streams"]):
        dest.unlink(missing_ok=True)
        raise PipelineError("clipe baixado sem stream de vídeo")
    return dest


def prepare_broll(brief: dict, cfg: dict, logger: Logger, offline: bool = False) -> list[dict]:
    """Devolve até `max_per_video` clipes (já baixados) com a origem registrada. Nunca derruba o vídeo:
    sem chave, sem tema, sem rede ou sem clipe adequado => lista vazia e o vídeo segue só com fotos."""
    b = cfg.get("broll") or {}
    key, _origin = read_secret(b.get("key_env", "PIXABAY_API_KEY"), [b.get("key_file", "APIpixabay")], PIXABAY_KEY)
    if not (b.get("enabled") and key):
        return []
    themes = themes_for(brief)
    if not themes:
        return []
    from product_fetcher import Http
    http = Http(cfg, logger, offline=offline)
    http.s = dict(http.s, min_delay_s=max(http.s["min_delay_s"], b.get("min_delay_s", 1.0)))
    demo = bool(b.get("demo"))
    # modo DEMONSTRAÇÃO (só --demo): aceita clipes que mostram um produto parecido e busca "pessoas usando"; nunca roda na rotina diária
    conflicts, out, used_ids = (set() if demo else conflict_words(brief)), [], set()
    prod_en = next((ens[0] for pt, ens in PRODUCT_WORDS_EN.items() if re.search(rf"\b{pt}", _norm(brief["product"]["name"]))), None)
    for t in themes:
        if len(out) >= b["max_per_video"]:
            break
        try:
            picked = None
            queries = ([("en", f"{prod_en} {t['queries'][1][1]}")] if (demo and prod_en) else []) + t["queries"]
            for lang, q in queries:
                picked = choose_hit(search_pixabay(http, key, q, lang, cfg), conflicts, cfg, used_ids)
                if picked:
                    break
            if not picked:
                logger.info("nenhum clipe adequado", tema=t["theme"])
                continue
            h, rend = picked["hit"], picked["rendition"]
            used_ids.add(h["id"])
            path = download_clip(http, rend, cache_dir(cfg) / "broll" / f"pixabay-{h['id']}-{rend['name']}.mp4", logger)
            out.append({"theme": t["theme"], "fact_id": t["fact_id"], "path": str(path), "provider": "pixabay",
                        "id": h["id"], "page_url": h.get("pageURL", ""), "user": h.get("user", ""), "tags": h.get("tags", ""),
                        "duration": h.get("duration"), "width": rend["width"], "height": rend["height"],
                        "rendition": rend["name"], "sha256": sha256_file(path), "fetched_at": iso()})
            logger.info("clipe de ambiente escolhido", tema=t["theme"], id=h["id"], autor=h.get("user"))
        except Exception as e:  # b-roll é opcional
            logger.warn("b-roll indisponível: o vídeo segue só com as fotos", tema=t["theme"], erro=str(e)[:160])
    return out


def credits_text(sb: dict) -> str:
    lines = ["Créditos dos clipes de ambiente (Pixabay):"]
    if sb["strategy"].get("demo"):
        lines.insert(0, "MODO DEMONSTRAÇÃO: os clipes podem mostrar um produto parecido (não o seu). Use só para avaliar; não publique sem revisar.")
    for s in sb["scenes"]:
        c = s.get("clip")
        if c:
            lines.append(f"- Cena {s['index']}: vídeo de {c['user']} via Pixabay (id {c['id']}) — {c['page_url']}")
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""
