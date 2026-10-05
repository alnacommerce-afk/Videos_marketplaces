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
    ("escola", r"\bescola\b|\bescolar\b", "escola", "school"),
    ("decoracao", r"\bdecor\w*", "decoração", "home decor"),
]

# Fato de uso que fala de crianças: só ele autoriza (com broll.allow_children) um clipe com criança
KIDS_PATTERN = re.compile(r"crian[cç]|infantil|pequen[oa]s?\b|filh[oa]s?\b|escola|escolar|\bkids?\b", re.I)
KID_TAGS = {"child", "children", "kid", "kids", "baby", "boy", "girl", "toddler", "teen"}

# palavras do produto -> equivalentes em inglês, para descartar clipes que mostrem OUTRO produto igual
PRODUCT_WORDS_EN = {"toalha": ["towel"], "tabua": ["cutting board", "board"], "colher": ["spoon"], "rolo": ["rolling pin"],
                    "top": ["top", "crop"], "madeira": ["wood", "wooden"], "faca": ["knife"], "panela": ["pot", "pan"],
                    "camiseta": ["shirt"], "legging": ["legging"], "bolsa": ["bag"], "copo": ["cup", "glass"]}


# Termos em inglês para medir PROXIMIDADE entre um clipe e o produto (nome + material confirmado). Só ranqueiam clipes;
# nada disto vira texto ou afirmação.
SIMILARITY_TYPE = {"toalha": ["towel", "bath towel", "beach towel"], "banho": ["bath", "bathroom"], "camiseta": ["t-shirt", "shirt"],
                   "top": ["crop top", "sportswear", "activewear"], "legging": ["leggings"], "tabua": ["cutting board", "chopping board"],
                   "colher": ["spoon", "wooden spoon"], "rolo": ["rolling pin"], "massa": ["dough"], "faca": ["knife"],
                   "panela": ["pot", "pan"], "copo": ["cup", "glass"], "bolsa": ["bag"]}
SIMILARITY_MATERIAL = {"algodao": ["cotton"], "poliester": ["polyester"], "elastano": ["spandex", "stretch"],
                       "microfibra": ["microfiber"], "madeira": ["wood", "wooden"], "bambu": ["bamboo"], "silicone": ["silicone"]}
# palavras do tema que aparecem em tudo (ex.: "home fitness" não é "home decor"): não contam como casamento de tema
GENERIC_THEME_WORDS = {"home", "person", "people"}
PEOPLE_TAGS = {"woman", "man", "person", "people", "couple", "female", "male", "lady", "adult", "athlete"}


def similarity_terms(brief: dict) -> dict:
    """primary = o que o produto É (tipo, do nome); extra = material (do nome ou de fatos de material utilizáveis)."""
    primary, extra = [], []
    toks = re.findall(r"[a-z]+", _norm(brief["product"]["name"]))
    for f in brief["confirmed_facts"]:
        if f["usable"] and f["kind"] == "material":
            toks += re.findall(r"[a-z]+", _norm(f["text"]))
    for tok in toks:
        for t in SIMILARITY_TYPE.get(tok, []):
            if t not in primary:
                primary.append(t)
        for t in SIMILARITY_MATERIAL.get(tok, []):
            if t not in extra:
                extra.append(t)
    return {"primary": primary, "extra": extra}


def score_hit(h: dict, idx: int, n: int, rank: dict) -> tuple[float, list[str]]:
    tags = {t.strip().lower() for t in (h.get("tags") or "").split(",") if t.strip()}
    tag_text = " ".join(tags)
    score, matched = 0.0, []
    sim = rank.get("sim") or {}
    prim = [t for t in sim.get("primary", []) if re.search(rf"\b{re.escape(t)}", tag_text)]
    if prim:
        score += 4
        matched += prim[:2]
    ext = [t for t in sim.get("extra", []) if re.search(rf"\b{re.escape(t)}", tag_text)]
    score += min(len(ext), 2)
    matched += ext[:2]
    thm = [w for w in rank.get("theme_words", []) if re.search(rf"\b{re.escape(w)}", tag_text)]
    if thm:
        score += 3
        matched += thm[:2]
    if rank.get("kids") and tags & KID_TAGS:
        score += 3
        matched.append("criança (uso infantil confirmado)")
    if rank.get("people") and tags & PEOPLE_TAGS:
        score += 2
        matched.append("pessoa")
    score += (n - idx) / max(n, 1)  # leve preferência pela popularidade (a API já ordena)
    return round(score, 2), matched


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
                out.append({"theme": theme, "fact_id": f["id"], "queries": [("pt", q_pt), ("en", q_en)],
                            "kids": bool(KIDS_PATTERN.search(f["text"]))})
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


def kids_allowed(cfg: dict, theme: dict) -> bool:
    """Criança no clipe só com a trava ligada (--demo) E um fato de uso confirmado que fale de crianças."""
    return bool(cfg.get("broll", {}).get("allow_children") and theme.get("kids"))


def choose_hit(hits: list[dict], conflicts: set[str], cfg: dict, skip_ids: set | frozenset = frozenset(),
               rank: dict | None = None, kids: bool = False) -> dict | None:
    """Sem `rank`: primeiro hit que passa nos filtros (rotina diária). Com `rank` ({sim, theme_words, people, min_score}):
    entre os que passam nos filtros, o de MAIOR proximidade com o produto/tema; abaixo de `min_score` nenhum serve."""
    b = cfg["broll"]
    avoid = {t.lower() for t in b["avoid_tags"]}
    if kids:  # uso infantil confirmado: libera as tags de criança, mas nunca rosto em primeiro plano
        avoid = (avoid - KID_TAGS) | {t.lower() for t in b.get("kids_extra_avoid", [])}
    ok = []
    for idx, h in enumerate(hits):
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
        if any(re.search(rf"\b{re.escape(a.lower())}", tag_text) for a in b.get("avoid_style_tags", [])):
            continue  # animação/desenho/3D: queremos uso real, com pessoas de verdade
        if any(re.search(rf"\b{re.escape(w)}", tag_text) for w in conflicts):
            continue
        cand = {"hit": h, "rendition": {"url": rend["url"], "width": rend["width"], "height": rend["height"],
                                         "size": rend.get("size", 0), "name": "large" if rend is big else "medium"}}
        if rank is None:
            return cand
        cand["score"], cand["matched"] = score_hit(h, idx, len(hits), rank)
        if not [m for m in cand["matched"] if m != "pessoa"]:
            continue  # só "tem gente" não basta: precisa casar com o produto ou com o tema do uso
        ok.append(cand)
    if not ok:
        return None
    best = max(ok, key=lambda c: c["score"])  # max devolve o primeiro em caso de empate
    return best if best["score"] >= rank.get("min_score", 0) else None


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
            kids = kids_allowed(cfg, t)
            theme_en = t["queries"][1][1]
            if demo:
                # DEMO: junta candidatos de várias buscas (produto+tema, pessoa+produto, pessoa+tema) e escolhe o MAIS PRÓXIMO do produto
                queries = ([("en", f"{prod_en} {theme_en}"), ("en", f"person {prod_en}")] if prod_en else []) + [("en", f"{theme_en} person")] + t["queries"]
                if kids:
                    queries = [("en", f"children {theme_en}"), ("en", f"kids {prod_en or ''} {theme_en}".replace("  ", " "))] + queries
                cands, seen = [], set()
                for lang, q in queries:
                    for h in search_pixabay(http, key, q, lang, cfg):
                        if h.get("id") not in seen:
                            seen.add(h.get("id"))
                            cands.append(h)
                rank = {"sim": similarity_terms(brief), "theme_words": [w for w in re.split(r"[ ,]+", theme_en) if w and w not in GENERIC_THEME_WORDS],
                        "people": True, "min_score": 3, "kids": kids}
                picked = choose_hit(cands, conflicts, cfg, used_ids, rank, kids=kids)
            else:
                for lang, q in t["queries"]:
                    picked = choose_hit(search_pixabay(http, key, q, lang, cfg), conflicts, cfg, used_ids, kids=kids)
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
                        "rendition": rend["name"], "sha256": sha256_file(path), "fetched_at": iso(), "kids_ok": kids,
                        **({"similarity": {"score": picked["score"], "matched": picked["matched"]}} if "score" in picked else {})})
            logger.info("clipe de ambiente escolhido", tema=t["theme"], id=h["id"], autor=h.get("user"),
                        similaridade=picked.get("score"), tags=h.get("tags"))
        except Exception as e:  # b-roll é opcional
            logger.warn("b-roll indisponível: o vídeo segue só com as fotos", tema=t["theme"], erro=str(e)[:160])
    return out


def credits_text(sb: dict) -> str:
    lines = ["Créditos dos clipes de ambiente (Pixabay):"]
    if sb["strategy"].get("demo"):
        lines.insert(0, "MODO DEMONSTRAÇÃO: os clipes podem mostrar um produto parecido (não o seu). Use só para avaliar; não publique sem revisar.")
    for s in sb["scenes"]:
        c = s.get("clip")
        if s.get("presenter"):
            lines.append(f"- Cena {s['index']}: embaixadora da marca gerada por IA (HeyGen), vídeo {c.get('video_id')}. Confira se o marketplace exige aviso de conteúdo gerado por IA.")
            continue
        if c:
            sim = c.get("similarity")
            extra = f" | proximidade {sim['score']} ({', '.join(sim['matched'])})" if sim else ""
            lines.append(f"- Cena {s['index']}: vídeo de {c['user']} via Pixabay (id {c['id']}) — {c['page_url']} | tags: {c.get('tags', '')}{extra}")
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""
