"""Product Fetcher: lê a loja ALNA (ou um catálogo manual) e monta o Product Brief.

Princípios:
  * Só entra no brief o que está publicado na fonte (ou foi escrito pelo usuário no catálogo).
  * Cada fato carrega a `source`. O texto do fato é SEMPRE literal da fonte.
  * Afirmações sensíveis (garantia, durabilidade, certificações, superlativos...) ficam
    marcadas `risk=true` e NÃO são usadas em vídeo sem confirmação manual.
  * Consulta educada: robots.txt, intervalo mínimo entre requisições, cache em disco.

Uso:  python product_fetcher.py discover | brief <url> | brief --catalog arquivo.json <id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from common import (Logger, PipelineError, cache_dir, iso, load_config, load_json, save_json,
                    sha256_file, slugify)

EXPECTED_KINDS = ["material", "dimension", "quantity", "color"]  # só para registrar o que faltou

# kind -> regex (classificação do trecho; o TEXTO nunca é reescrito)
KIND_RULES = [
    ("gift", r"\bpresent(e|ear|eie)\b"),
    ("dimension", r"\d+[.,]?\d*\s*(x|×|por)\s*\d+|\b\d+[.,]?\d*\s*(cm|mm|metros?|litros?|ml|kg)\b|\b(altura|largura|comprimento|di[aâ]metro|profundidade|medidas?|tamanho|capacidade)\b"),
    ("quantity", r"\b(kit|conjunto|jogo)\b|\b\d+\s*(unidades?|un\.?|pe[cç]as?|p[cç]s|pares?|toalhas?)\b"),
    ("material", r"algod[aã]o|bambu|madeira|\ba[cç]o\b|inox|pl[aá]stico|silicone|vidro|cer[aâ]mica|microfibra|poli[eé]ster|couro|metal|alum[ií]nio|porcelana|resina|tecido|linho|nylon|n[aá]ilon|borracha|acr[ií]lico|polipropileno|\bmdf\b|pinus|eucalipto|\bmaterial\b"),
    ("color", r"\bcor(es)?\b|\b(preto|branco|azul|vermelho|rosa|verde|amarelo|cinza|bege|marrom|laranja|roxo|dourado|prata|rubi)\b"),
    ("use", r"\b(ideal para|serve para|indicad[oa] para|perfeit[oa] para|use para|usar para|para uso|para usar)\b"),
]

# Trechos que viram "risco": o usuário precisa confirmar por escrito (confirmed:true no catálogo).
RISK_PATTERN = re.compile(
    r"\b(melhor|n[úu]mero ?1|l[ií]der|garanti\w*|certific\w*|inmetro|anvisa|aprovad\w*|testad\w*|"
    r"comprovad\w*|cient[ií]fic\w*|dermatol\w*|hipoalerg\w*|antibacteri\w*|antial[eé]rgic\w*|"
    r"dur[aá]vel|durabilidade|resistente|resist[eê]ncia|indestrut\w*|inquebr\w*|n[aã]o (risca|quebra|desbota|"
    r"amassa|encolhe|solta)|vitalic\w*|[uú]nico no mercado|100% (seguro|atóxic\w*)|at[oó]xic\w*|"
    r"frete gr[aá]tis|promo[cç][aã]o|desconto|oferta|compre agora|estoque|ultimas? unidades)\b", re.I)

SKIP_IMG = re.compile(r"(logo|icon|sprite|avatar|favicon|banner|placeholder|loading|pixel|badge|selo|payment|flag)", re.I)
PRODUCT_LINK = re.compile(r"/(produtos?|products?|p|item|itens|loja/[^/]+)/[^/?#]+", re.I)


# ----------------------------------------------------------------------------
# HTTP educado (robots + delay + cache)
# ----------------------------------------------------------------------------
class Http:
    def __init__(self, cfg: dict, logger: Logger | None = None, offline: bool = False):
        import requests  # import tardio: o resto do módulo funciona sem rede
        self.requests = requests
        self.s = cfg["store"]
        self.log = logger or Logger(echo=False)
        self.cache = cache_dir(cfg) / "http"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.s["user_agent"]
        self._last = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.offline = offline

    def _allowed(self, url: str) -> bool:
        host = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(host + "/robots.txt", timeout=self.s["timeout_s"])
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[host] = rp
                else:
                    self._robots[host] = None  # sem robots.txt = sem restrição declarada
            except Exception:
                self._robots[host] = None
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch(self.s["user_agent"], url)

    def get(self, url: str, binary: bool = False, ttl_hours: float | None = None):
        ttl = self.s["cache_ttl_hours"] if ttl_hours is None else ttl_hours
        key = hashlib.sha1(url.encode()).hexdigest()
        cf = self.cache / f"{key}.json"
        if not binary and cf.exists():
            c = json.loads(cf.read_text(encoding="utf-8"))
            age_h = (time.time() - c["ts"]) / 3600
            if age_h <= ttl or self.offline:
                return c["text"]
        if self.offline:
            raise PipelineError(f"Modo offline e sem cache para {url}")
        if not self._allowed(url):
            raise PipelineError(f"robots.txt não permite acessar {url}")
        wait = self.s["min_delay_s"] - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        try:
            r = self.session.get(url, timeout=self.s["timeout_s"])
        except self.requests.RequestException as e:
            raise PipelineError(f"Falha de rede em {url}: {e}") from e
        if r.status_code != 200:
            raise PipelineError(f"HTTP {r.status_code} em {url}")
        if binary:
            return r
        if "charset" not in r.headers.get("content-type", "").lower():
            r.encoding = "utf-8"  # sem charset no cabeçalho o requests assume latin-1 e quebra acentos
        cf.write_text(json.dumps({"url": url, "ts": time.time(), "text": r.text}, ensure_ascii=False), encoding="utf-8")
        return r.text


# ----------------------------------------------------------------------------
# Parsing de HTML (stdlib)
# ----------------------------------------------------------------------------
class PageParser(HTMLParser):
    SKIP_TEXT = {"script", "style", "noscript", "nav", "footer", "header", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.links, self.imgs = {}, [], []
        self.jsonld, self.json_scripts = [], []
        self.title, self.h1, self.blocks = "", [], []
        self._stack, self._buf, self._script_attrs, self._cur_text = [], [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._stack.append(tag)
        if tag == "meta":
            k = a.get("property") or a.get("name")
            if k and a.get("content"):
                self.meta.setdefault(k.lower(), a["content"])
        elif tag == "a" and a.get("href"):
            self.links.append({"href": a["href"], "text": ""})
        elif tag == "img":
            cands = [a.get("src"), a.get("data-src"), a.get("data-lazy-src")]
            for part in (a.get("srcset") or a.get("data-srcset") or "").split(","):
                cands.append(part.strip().split(" ")[0] if part.strip() else None)
            for c in filter(None, cands):
                self.imgs.append({"src": c, "alt": a.get("alt", ""), "w": a.get("width"), "h": a.get("height")})
        elif tag == "script":
            self._script_attrs, self._buf = a, []
        elif tag == "link" and a.get("rel") == "next" and a.get("href"):
            self.meta["rel-next"] = a["href"]

    def handle_endtag(self, tag):
        if tag == "script" and self._script_attrs is not None:
            body = "".join(self._buf).strip()
            t = (self._script_attrs.get("type") or "").lower()
            if body and "ld+json" in t:
                self.jsonld.append(body)
            elif body and (t == "application/json" or self._script_attrs.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__")):
                self.json_scripts.append(body)
            elif body and re.match(r"window\.__\w+__\s*=\s*\{", body):
                self.json_scripts.append(body.split("=", 1)[1].rstrip("; \n"))
            self._script_attrs = None
        if tag in ("p", "li", "h2", "h3", "td", "dd") and self._cur_text:
            txt = " ".join("".join(self._cur_text).split())
            if txt:
                self.blocks.append(txt)
            self._cur_text = []
        while self._stack and self._stack[-1] != tag:
            self._stack.pop()
        if self._stack:
            self._stack.pop()

    def handle_data(self, data):
        if self._script_attrs is not None:
            self._buf.append(data)
            return
        if self._stack and self._stack[-1] == "title":
            self.title += data
        if self.links and "a" in self._stack:
            self.links[-1]["text"] += data
        if "h1" in self._stack and data.strip():
            self.h1.append(data.strip())
        if not (set(self._stack) & self.SKIP_TEXT) and set(self._stack) & {"p", "li", "h2", "h3", "td", "dd"}:
            self._cur_text.append(data)


def parse_html(html: str) -> PageParser:
    p = PageParser()
    p.feed(html)
    return p


def _loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def _walk(obj, depth=0):
    if depth > 12:
        return
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, depth + 1)


def _as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def _img_url(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("url", "src", "contentUrl", "image_url", "original"):
            if isinstance(x.get(k), str):
                return x[k]
    return None


def normalize_product_dict(d: dict, base_url: str = "") -> dict | None:
    """Converte um dict 'parecido com produto' (JSON-LD, JSON embutido, API) para o formato interno."""
    name = d.get("name") or d.get("title") or d.get("nome")
    if not isinstance(name, str) or not name.strip():
        return None
    imgs = []
    for k in ("image", "images", "imagens", "photos", "gallery", "image_url", "imageUrl", "cover", "thumbnail"):
        for it in _as_list(d.get(k)):
            u = _img_url(it)
            if u:
                imgs.append(urljoin(base_url, u))
    desc = d.get("description") or d.get("descricao") or d.get("descrição") or ""
    if not isinstance(desc, str):
        desc = ""
    attrs = []
    for ap in _as_list(d.get("additionalProperty")):
        if isinstance(ap, dict) and ap.get("name") and ap.get("value") not in (None, ""):
            attrs.append((str(ap["name"]), str(ap["value"])))
    for k, label in (("material", "Material"), ("color", "Cor"), ("size", "Tamanho"), ("weight", "Peso"),
                     ("cor", "Cor"), ("tamanho", "Tamanho")):
        v = d.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("value")
        if isinstance(v, (str, int, float)) and str(v).strip():
            attrs.append((label, str(v)))
    price = None
    offers = d.get("offers")
    for o in _as_list(offers):
        if isinstance(o, dict) and o.get("price") not in (None, ""):
            price = {"value": str(o["price"]), "currency": o.get("priceCurrency", "BRL")}
    if price is None and d.get("price") not in (None, "") and isinstance(d.get("price"), (str, int, float)):
        price = {"value": str(d["price"]), "currency": "BRL"}
    url = d.get("url") or d.get("link") or ""
    if not url and d.get("slug"):
        url = f"/produto/{d['slug']}"
    cat = d.get("category") or d.get("categoria") or ""
    if isinstance(cat, dict):
        cat = cat.get("name", "")
    return {"id": str(d.get("sku") or d.get("id") or d.get("slug") or ""), "name": name.strip(),
            "category": str(cat), "url": urljoin(base_url, url) if url else "", "images": list(dict.fromkeys(imgs)),
            "description": desc.strip(), "attributes": attrs, "price": price}


def products_from_json(obj, base_url: str = "") -> list[dict]:
    """Procura, em qualquer JSON, dicts que pareçam produtos (nome + imagem/descrição)."""
    out = []
    for node in _walk(obj):
        if not isinstance(node, dict):
            continue
        t = node.get("@type")
        looks = t == "Product" or (isinstance(t, list) and "Product" in t) or (
            ("name" in node or "title" in node or "nome" in node) and any(
                k in node for k in ("image", "images", "imagens", "image_url", "imageUrl", "photos"))
            and any(k in node for k in ("description", "descricao", "price", "offers", "sku", "slug", "id")))
        if looks:
            p = normalize_product_dict(node, base_url)
            if p and (p["images"] or p["description"]):
                out.append(p)
    # remove duplicados por nome+url
    seen, uniq = set(), []
    for p in out:
        k = (p["name"], p["url"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def extract_product_from_html(html: str, url: str) -> dict:
    """JSON-LD → JSON embutido → OpenGraph/DOM. Retorna o produto cru (não é o brief ainda)."""
    page = parse_html(html)
    cands = []
    for raw in page.jsonld + page.json_scripts:
        data = _loads(raw)
        if data is not None:
            cands += products_from_json(data, url)
    prod = None
    if cands:
        # o candidato com mais informação, preferindo o que tem a mesma URL
        cands.sort(key=lambda p: (p["url"].rstrip("/") == url.rstrip("/"), len(p["description"]), len(p["images"])), reverse=True)
        prod = cands[0]
    if prod is None:
        name = page.meta.get("og:title") or (page.h1[0] if page.h1 else page.title.strip())
        if not name:
            raise PipelineError(f"Não encontrei dados de produto em {url} (página renderizada no navegador?).")
        prod = {"id": "", "name": name, "category": "", "url": url, "images": [], "description": "",
                "attributes": [], "price": None}
    # complementos
    if not prod["description"]:
        prod["description"] = page.meta.get("og:description") or page.meta.get("description") or ""
    if len(prod["description"]) < 40 and page.blocks:
        prod["description"] = "\n".join(b for b in page.blocks if 8 <= len(b) <= 400)
    og = page.meta.get("og:image")
    if og:
        prod["images"].insert(0, urljoin(url, og))
    if len(prod["images"]) < 2:
        for im in page.imgs:
            src = urljoin(url, im["src"])
            if SKIP_IMG.search(src) or src.lower().endswith(".svg"):
                continue
            prod["images"].append(src)
    prod["images"] = list(dict.fromkeys(prod["images"]))
    prod["url"] = prod["url"] or url
    return prod


def discover_product_urls(http: Http, cfg: dict, logger: Logger) -> list[str]:
    s = cfg["store"]
    base = s["base_url"].rstrip("/")
    list_url = base + s["list_path"]
    urls: list[str] = []
    seen_pages = set()
    page_url, pages = list_url, 0
    while page_url and page_url not in seen_pages and pages < 6:
        seen_pages.add(page_url)
        pages += 1
        html = http.get(page_url)
        parsed = parse_html(html)
        found = []
        for raw in parsed.jsonld + parsed.json_scripts:
            data = _loads(raw)
            if data is not None:
                found += [p["url"] for p in products_from_json(data, page_url) if p["url"]]
        for l in parsed.links:
            full = urljoin(page_url, l["href"]).split("#")[0]
            if urlparse(full).netloc == urlparse(base).netloc and PRODUCT_LINK.search(urlparse(full).path) \
                    and urlparse(full).path.rstrip("/") != urlparse(list_url).path.rstrip("/"):
                found.append(full)
        urls += found
        nxt = parsed.meta.get("rel-next")
        if not nxt:
            for l in parsed.links:
                if re.search(r"pr[oó]xima|next|›|»", l["text"], re.I):
                    nxt = l["href"]
                    break
        page_url = urljoin(page_url, nxt) if nxt else None
    if not urls:  # sitemap como segunda tentativa
        try:
            sm = http.get(base + "/sitemap.xml")
            urls = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm) if PRODUCT_LINK.search(urlparse(u).path)]
        except PipelineError:
            pass
    urls = list(dict.fromkeys(urls))[: s["max_products"]]
    if not urls:
        raise PipelineError(
            f"Nenhum produto encontrado em {list_url}. Se a loja é renderizada no navegador (SPA), o HTML não traz "
            "os produtos: informe um endpoint JSON em config.store.json_endpoint ou use um catálogo manual "
            "(--catalog templates/catalog.example.json).")
    logger.info("produtos descobertos", count=len(urls))
    return urls


# ----------------------------------------------------------------------------
# Fatos
# ----------------------------------------------------------------------------
_EMOJI = re.compile("[\U00010000-\U0010ffff☀-➿⬀-⯿️‍]")
_BULLET = re.compile(r"^[\s•·▪●○◦■□✔✅✓☑➤➔→\-–—*]+")


def clean_display(text: str) -> str:
    t = _EMOJI.sub("", text)
    t = _BULLET.sub("", t)
    return " ".join(t.split()).strip(" .;:")


def split_units(description: str) -> list[str]:
    units = []
    for line in re.split(r"[\r\n]+", description or ""):
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])", line):
            for part in re.split(r"\s*[;|•]\s*", sent):
                part = part.strip()
                if len(clean_display(part)) >= 4:
                    units.append(part)
    return units


def classify(text: str) -> str:
    for kind, pat in KIND_RULES:
        if re.search(pat, text, re.I):
            return kind
    return "characteristic"


MAX_DISPLAY = 64


def build_facts(raw: dict, show_price: bool = False) -> tuple[list[dict], list[str]]:
    facts: list[dict] = []
    seen: set[str] = set()

    def add(kind, text, source, risk=False, confirmed=False, display=None):
        key = clean_display(text).lower()
        if not key or key in seen:
            return
        seen.add(key)
        disp = display if display is not None else clean_display(text)
        facts.append({"id": f"f{len(facts) + 1}", "kind": kind, "text": clean_display(text),
                      "display": disp if disp and len(disp) <= MAX_DISPLAY else None,
                      "source": source, "risk": bool(risk and not confirmed),
                      "usable": not (risk and not confirmed)})

    # 1) fatos escritos pelo usuário no catálogo = confirmados por escrito
    for mf in raw.get("manual_facts", []):
        add(mf["kind"], mf["text"], "manual:catalogo", risk=False, confirmed=True)
    # 2) atributos estruturados da loja
    for k, v in raw.get("attributes", []):
        text = f"{k}: {v}"
        kind = classify(text)
        add(kind if kind != "characteristic" else "characteristic", text, "loja:atributo",
            risk=bool(RISK_PATTERN.search(text)))
    # 3) descrição publicada, trecho a trecho (literal)
    for u in split_units(raw.get("description", "")):
        add(classify(u), u, "loja:descricao", risk=bool(RISK_PATTERN.search(u)))
    # 4) preço só como fato; só é usado quando brand.show_price = true
    pr = raw.get("price")
    if pr and pr.get("value"):
        try:
            val = float(str(pr["value"]).replace(",", "."))
            txt = ("R$ " + f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if pr.get("currency", "BRL") == "BRL" else f"{val:.2f} {pr['currency']}"
            add("price", txt, "loja:preco")
            facts[-1]["usable"] = bool(show_price)
        except ValueError:
            pass
    # nome do produto não é "fato": já fica em product.name
    facts = [f for f in facts if f["text"].lower() != raw.get("name", "").lower()]
    for i, f in enumerate(facts, 1):
        f["id"] = f"f{i}"
    missing = [k for k in EXPECTED_KINDS if not any(f["kind"] == k and f["usable"] for f in facts)]
    return facts, missing


def selling_angles(facts: list[dict]) -> list[dict]:
    """Ângulos de venda = rótulos de organização, derivados de fatos usáveis. Não criam claims."""
    by = {}
    for f in facts:
        if f["usable"]:
            by.setdefault(f["kind"], []).append(f["id"])
    names = {"dimension": "clareza de tamanho", "material": "material informado", "quantity": "o que vem na embalagem",
             "color": "opções de cor", "use": "uso / ocasião", "gift": "presente", "characteristic": "característica informada",
             "contents": "conteúdo", "problem": "problema informado", "before": "antes", "after": "depois",
             "comparison": "comparação informada"}
    return [{"angle": names.get(k, k), "kind": k, "fact_ids": ids} for k, ids in by.items() if k != "price"]


# ----------------------------------------------------------------------------
# Imagens + brief
# ----------------------------------------------------------------------------
def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    for k, v in (("jpeg", ".jpg"), ("jpg", ".jpg"), ("png", ".png"), ("webp", ".webp")):
        if k in ct:
            return v
    m = re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url, re.I)
    return "." + m.group(1).lower().replace("jpeg", "jpg") if m else ".jpg"


def fetch_images(http: Http | None, sources: list[str], dest: Path, max_images: int, logger: Logger,
                 base_dir: Path | None = None) -> list[dict]:
    from PIL import Image
    dest.mkdir(parents=True, exist_ok=True)
    out, hashes = [], set()
    for i, src in enumerate(sources):
        if len(out) >= max_images:
            break
        try:
            if re.match(r"https?://", src):
                if http is None:
                    continue
                r = http.get(src, binary=True)
                if len(r.content) > 15 * 1024 * 1024:
                    raise PipelineError("imagem acima de 15MB")
                path = dest / f"img_{len(out) + 1:02d}{_ext_for(r.headers.get('content-type', ''), src)}"
                path.write_bytes(r.content)
            else:
                p = Path(src)
                p = p if p.is_absolute() else (base_dir or Path.cwd()) / p
                if not p.exists():
                    raise PipelineError("arquivo local inexistente")
                path = dest / f"img_{len(out) + 1:02d}{p.suffix.lower() or '.jpg'}"
                path.write_bytes(p.read_bytes())
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                w, h = im.size
            if min(w, h) < 300:
                path.unlink()
                logger.warn("imagem pequena demais descartada", src=src, size=f"{w}x{h}")
                continue
            digest = sha256_file(path)
            if digest in hashes:
                path.unlink()
                continue
            hashes.add(digest)
            out.append({"path": str(path), "url": src, "sha256": digest, "width": w, "height": h,
                        "is_cover": len(out) == 0})
        except Exception as e:  # imagem ruim não derruba o produto inteiro
            logger.warn("imagem ignorada", src=src, motivo=str(e)[:120])
    return out


def build_brief(raw: dict, cfg: dict, http: Http | None, logger: Logger, base_dir: Path | None = None) -> dict:
    pid = slugify(raw.get("id") or urlparse(raw.get("url", "")).path.rstrip("/").split("/")[-1] or raw["name"], 60)
    dest = cache_dir(cfg) / "products" / pid
    images = fetch_images(http, raw.get("images", []), dest, cfg["store"]["max_images"], logger, base_dir)
    if not images:
        raise PipelineError(f"Produto '{raw['name']}' sem imagem utilizável — vídeo não será gerado.")
    facts, missing = build_facts(raw, cfg["brand"].get("show_price", False))
    for kind in missing:
        logger.warn("informação não disponível na fonte", produto=raw["name"], informacao=kind)
    risky = [f for f in facts if f["risk"]]
    for f in risky:
        logger.warn("afirmação sensível sem confirmação manual: não será usada", produto=raw["name"], trecho=f["text"][:80])
    brief = {
        "schema": 1,
        "fetched_at": iso(),
        "product": {"id": pid, "name": raw["name"], "category": raw.get("category", ""), "url": raw.get("url", ""),
                    "images": images, "description": raw.get("description", "")},
        "confirmed_facts": facts,
        "unavailable": missing,
        "selling_angles": selling_angles(facts),
        "video_strategy": {},
    }
    save_json(dest / "brief.json", brief)
    return brief


# ----------------------------------------------------------------------------
# Fontes: loja / catálogo manual
# ----------------------------------------------------------------------------
def load_catalog(path: Path) -> list[dict]:
    data = load_json(path)
    out = []
    for p in data.get("products", []):
        out.append({"id": p.get("id", ""), "name": p["name"], "category": p.get("category", ""), "url": p.get("url", ""),
                    "images": p.get("images", []), "description": p.get("description", ""),
                    "attributes": [], "price": p.get("price"), "manual_facts": p.get("facts", []),
                    "_base": str(Path(path).parent)})
    return out


def list_products(cfg: dict, logger: Logger, catalog: Path | None = None, offline: bool = False) -> list[dict]:
    """Retorna produtos 'crus' (ainda sem baixar imagens). Para a loja, descobre URLs e lê cada página."""
    if catalog:
        return load_catalog(catalog)
    http = Http(cfg, logger, offline=offline)
    ep = cfg["store"].get("json_endpoint")
    if ep:
        data = _loads(http.get(ep))
        prods = products_from_json(data, cfg["store"]["base_url"]) if data is not None else []
        if prods:
            return prods[: cfg["store"]["max_products"]]
    raws = []
    for u in discover_product_urls(http, cfg, logger):
        try:
            raws.append(extract_product_from_html(http.get(u), u))
        except PipelineError as e:
            logger.warn("produto ignorado", url=u, motivo=str(e)[:160])
    return raws


def get_brief(raw: dict, cfg: dict, logger: Logger, http: Http | None = None, offline: bool = False) -> dict:
    http = http or (None if raw.get("_base") and not any(str(i).startswith("http") for i in raw.get("images", []))
                    else Http(cfg, logger, offline=offline))
    return build_brief(raw, cfg, http, logger, base_dir=Path(raw["_base"]) if raw.get("_base") else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["discover", "brief"])
    ap.add_argument("target", nargs="?", help="URL do produto ou id (no catálogo)")
    ap.add_argument("--catalog", type=Path)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    cfg, log = load_config(), Logger("fetcher")
    try:
        raws = list_products(cfg, log, a.catalog, a.offline)
        if a.cmd == "discover":
            for r in raws[: a.limit]:
                print(f"{r['name']}\t{r.get('url', '')}\t{len(r.get('images', []))} imagens")
            return 0
        pick = next((r for r in raws if a.target in (r.get("id"), r.get("url"), r["name"])), None)
        if pick is None and a.target and a.target.startswith("http") and not a.catalog:
            pick = extract_product_from_html(Http(cfg, log).get(a.target), a.target)
        if pick is None:
            raise PipelineError(f"Produto '{a.target}' não encontrado.")
        print(json.dumps(get_brief(pick, cfg, log, offline=a.offline), ensure_ascii=False, indent=2))
        return 0
    except PipelineError as e:
        log.error(str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
