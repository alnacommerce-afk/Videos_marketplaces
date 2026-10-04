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
import os
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

    def download(self, url: str, dest: Path, max_mb: int = 300) -> Path:
        """Baixa um arquivo servido pela API (ex.: clipe) em streaming, com limite de tamanho. Escreve em .part e renomeia."""
        wait = self.s["min_delay_s"] - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        part = Path(str(dest) + ".part")
        try:
            with self.session.get(url, stream=True, timeout=max(self.s["timeout_s"], 60)) as r:
                if r.status_code != 200:
                    raise PipelineError(f"HTTP {r.status_code} ao baixar o arquivo")
                total = 0
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        total += len(chunk)
                        if total > max_mb * 1024 * 1024:
                            raise PipelineError(f"arquivo acima de {max_mb} MB")
                        f.write(chunk)
        except self.requests.RequestException as e:
            part.unlink(missing_ok=True)
            raise PipelineError(f"Falha de rede ao baixar: {e}") from e
        except PipelineError:
            part.unlink(missing_ok=True)
            raise
        os.replace(part, dest)
        return dest

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None, ttl_hours: float = 1.0):
        """GET de uma API JSON (usa cache curto: o estoque muda). Respeita o intervalo mínimo entre requisições."""
        from urllib.parse import urlencode
        full = url + ("?" + urlencode(params) if params else "")
        key = hashlib.sha1((full + json.dumps(sorted((headers or {}).items()))).encode()).hexdigest()  # chave errada não pega cache da certa
        cf = self.cache / f"{key}.api.json"
        if cf.exists() and (self.offline or (time.time() - cf.stat().st_mtime) / 3600 <= ttl_hours):
            return json.loads(cf.read_text(encoding="utf-8"))
        if self.offline:
            raise PipelineError(f"Modo offline e sem cache para {url}")
        wait = self.s["min_delay_s"] - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        try:
            r = self.session.get(full, headers=headers or {}, timeout=self.s["timeout_s"])
        except self.requests.RequestException as e:
            raise PipelineError(f"Falha de rede em {url}: {e}") from e
        if r.status_code != 200:
            raise PipelineError(f"API HTTP {r.status_code} em {url}: {r.text[:160]}")
        r.encoding = "utf-8"
        data = r.json()
        cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

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
# API da própria loja (Supabase/PostgREST): dados estruturados, com estoque e ordem das fotos
# ----------------------------------------------------------------------------
IMAGE_ROLE_HINTS = [  # (papel, regex no texto alternativo da foto) — só ajuda a escolher o ENQUADRAMENTO
    ("detail", r"\b(close|detalhe|textura|zoom|macro|costura|acabamento)\b"),
    ("packaging", r"\b(embalagem|caixa|presente|kit)\b"),
    ("lifestyle", r"\b(pessoa|usando|mulher|homem|mesa|cozinha|praia|ambiente|estendid\w+|sobre|ao lado)\b"),
]


def image_role(alt: str) -> str:
    for role, pat in IMAGE_ROLE_HINTS:
        if re.search(pat, alt or "", re.I):
            return role
    return "product"


def supabase_products(cfg: dict, logger: Logger, offline: bool = False) -> list[dict] | None:
    """Lê os produtos PUBLICADOS pela API pública da loja. Retorna None se a API não estiver configurada."""
    sb = cfg["store"].get("supabase") or {}
    key = os.environ.get(sb.get("key_env", ""), "") or sb.get("publishable_key", "")
    if not (sb.get("enabled") and sb.get("url") and key):
        return None
    http = Http(cfg, logger, offline=offline)
    select = ("id,title,slug,description,status,video_url,category:categories(name),"
              "product_images(storage_path,alt_text,position),product_variants(name,price_cents,stock_quantity)")
    rows = http.get_json(sb["url"].rstrip("/") + "/rest/v1/products",
                         {"select": select, "status": "eq.published", "order": "created_at.desc",
                          "limit": str(cfg["store"]["max_products"])},
                         headers={"apikey": key, "Accept": "application/json"})
    base = cfg["store"]["base_url"].rstrip("/")
    prefix = f"{sb['url'].rstrip('/')}/storage/v1/object/public/{sb.get('bucket', 'product-media')}/"
    out = []
    for r in rows:
        imgs = sorted(r.get("product_images") or [], key=lambda i: i.get("position", 0))
        variants = r.get("product_variants") or []
        prices = [v["price_cents"] for v in variants if v.get("price_cents") is not None]
        meta = {prefix + i["storage_path"]: {"alt": i.get("alt_text") or "", "role": image_role(i.get("alt_text") or ""),
                                              "position": i.get("position", 0)} for i in imgs}
        out.append({"id": r["slug"], "name": r["title"], "category": (r.get("category") or {}).get("name", ""),
                    "url": f"{base}/produto/{r['slug']}", "images": list(meta), "image_meta": meta,
                    "description": r.get("description") or "", "attributes": [],
                    "price": {"value": f"{min(prices) / 100:.2f}", "currency": "BRL"} if prices else None,
                    "stock": sum(v.get("stock_quantity") or 0 for v in variants) if variants else None,
                    "variants": [v.get("name") for v in variants], "video_url": r.get("video_url"), "source": "api"})
    logger.info("produtos lidos pela API da loja", count=len(out), sem_estoque=sum(1 for p in out if p["stock"] == 0))
    return out


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

_BULLET_START = re.compile(r"^\s*([•·▪●○◦■□✔✅✓☑➤➔→\-–—*]|[\U00010000-\U0010ffff]|[\u2600-\u27bf\u2b00-\u2bff])")
_NOTE_START = re.compile(r"^(observa[cç][aã]o|importante|aten[cç][aã]o|aviso|obs\b\.?)\s*:?", re.I)
_LABEL_KIND = [
    (r"^(tamanho|medidas?|dimens\w+|largura|altura|comprimento|profundidade|di[aâ]metro|capacidade)\b", "dimension"),
    (r"^(composi\w+|material|tecido)\b", "material"),
    (r"^(cor|cores)\b", "color"),
    (r"^(conte[úu]do|itens inclu\w+|acompanha)\b", "contents"),
    (r"^(gramatura|peso)\b", "characteristic"),
]
_HAS_UNIT = re.compile(r"\b\d+[.,]?\d*\s*(cm|mm|m|kg|g|ml|l|litros?|metros?|un|unidades?)\b|\d+\s*[x×]\s*\d+", re.I)


def parse_description(desc: str) -> list[dict]:
    """Lê a descrição PRESERVANDO a estrutura (linhas, títulos, marcadores) e devolve unidades literais:
    {text, kind, approx, note, drop}. Títulos/perguntas ('Para quem é?', 'Dois lados, duas funções') não viram fato;
    observações ('Observação: ...') ficam registradas mas não são usadas no vídeo; medidas sem unidade são retidas."""
    lines = desc.splitlines()
    n, section, out = len(lines), "", []
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        text = clean_display(s)
        if len(text) < 3:
            continue
        had_bullet = bool(_BULLET_START.match(s))
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i + 1 >= n or not lines[i + 1].strip()
        words = len(text.split())
        raw_end = _BULLET_START.sub("", s).rstrip()  # clean_display tira ".:" do fim: a pontuação vem da linha ORIGINAL
        no_stop = not re.search(r"[.!]$", raw_end)
        mid_colon = ":" in raw_end.rstrip(":")
        substantive = bool(RISK_PATTERN.search(text) or _HAS_UNIT.search(text))  # medida ou trecho de risco nunca é "só um título"
        heading = (raw_end.endswith("?") or raw_end.endswith(":")
                   or (not substantive and next_blank and not had_bullet and words <= 8 and no_stop and not mid_colon)
                   or (not substantive and prev_blank and next_blank and words <= 14 and no_stop and not mid_colon))
        if heading:
            section = text.rstrip(":?").strip().lower()
            continue
        if _NOTE_START.match(text):
            out.append({"text": text, "kind": "note", "approx": False, "note": True, "drop": "observação (não usada em vídeo)"})
            continue
        pieces = [text]
        if not had_bullet and (words > 14 or not no_stop):  # parágrafo: vira frases
            pieces = [p.strip() for p in re.split(r"(?<=[.!])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])", text) if len(p.strip()) >= 4]
        for piece in pieces:
            for part in re.split(r"\s*[;|]\s*", piece):
                part = part.strip().strip(".")
                if len(part) < 4:
                    continue
                kind = None
                for pat, k in _LABEL_KIND:
                    if re.match(pat, part, re.I):
                        kind = k
                        break
                if kind is None and "embalagem" in section:
                    kind = "contents"
                if kind is None and "medida" in section and _HAS_UNIT.search(part):
                    kind = "dimension"
                kind = kind or classify(part)
                drop = None
                if kind == "dimension" and re.search(r"\d", part) and not _HAS_UNIT.search(part):
                    kind, drop = "characteristic", "medida sem unidade (ambígua)"
                out.append({"text": part, "kind": kind, "approx": "aproximad" in section and kind == "dimension",
                            "note": False, "drop": drop})
    return out


def build_facts(raw: dict, show_price: bool = False) -> tuple[list[dict], list[str]]:
    facts: list[dict] = []
    seen: set[str] = set()

    def add(kind, text, source, risk=False, confirmed=False, display=None, usable=True, approx=False, why=None):
        key = clean_display(text).lower()
        if not key or key in seen:
            return
        seen.add(key)
        disp = display if display is not None else clean_display(text)
        if approx and disp:
            disp = "Aprox. " + disp  # a fonte diz 'medidas aproximadas': não podemos mostrar como exatas
        ok = usable and not (risk and not confirmed)
        f = {"id": f"f{len(facts) + 1}", "kind": kind, "text": clean_display(text),
             "display": disp if disp and len(disp) <= MAX_DISPLAY else None,
             "source": source, "risk": bool(risk and not confirmed), "usable": ok}
        if approx:
            f["approx"] = True
        if why:
            f["reason"] = why
        facts.append(f)

    # 1) fatos escritos pelo usuário no catálogo = confirmados por escrito
    for mf in raw.get("manual_facts", []):
        add(mf["kind"], mf["text"], "manual:catalogo", risk=False, confirmed=True)
    # 2) atributos estruturados da loja
    for k, v in raw.get("attributes", []):
        text = f"{k}: {v}"
        add(classify(text), text, "loja:atributo", risk=bool(RISK_PATTERN.search(text)))
    # 3) descrição publicada: com estrutura (linhas) lemos linha a linha; achatada (HTML/meta) cai no divisor de frases
    desc = raw.get("description", "")
    if "\n" in desc.strip():
        for u in parse_description(desc):
            add(u["kind"], u["text"], "loja:descricao", risk=bool(RISK_PATTERN.search(u["text"])),
                usable=not u["drop"], approx=u["approx"], why=u["drop"])
    else:
        for u in split_units(desc):
            add(classify(u), u, "loja:descricao", risk=bool(RISK_PATTERN.search(u)))
    # 4) preço só como fato; só é usado quando brand.show_price = true
    pr = raw.get("price")
    if pr and pr.get("value"):
        try:
            val = float(str(pr["value"]).replace(",", "."))
            txt = ("R$ " + f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if pr.get("currency", "BRL") == "BRL" else f"{val:.2f} {pr['currency']}"
            add("price", txt, "loja:preco", usable=bool(show_price))
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
                 base_dir: Path | None = None, meta: dict | None = None) -> list[dict]:
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
            m = (meta or {}).get(src, {})
            out.append({"path": str(path), "url": src, "sha256": digest, "width": w, "height": h,
                        "is_cover": len(out) == 0, "alt": m.get("alt", ""), "role": m.get("role", "product")})
        except Exception as e:  # imagem ruim não derruba o produto inteiro
            logger.warn("imagem ignorada", src=src, motivo=str(e)[:120])
    return out


def build_brief(raw: dict, cfg: dict, http: Http | None, logger: Logger, base_dir: Path | None = None) -> dict:
    pid = slugify(raw.get("id") or urlparse(raw.get("url", "")).path.rstrip("/").split("/")[-1] or raw["name"], 60)
    dest = cache_dir(cfg) / "products" / pid
    images = fetch_images(http, raw.get("images", []), dest, cfg["store"]["max_images"], logger, base_dir, raw.get("image_meta"))
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
                    "images": images, "description": raw.get("description", ""), "stock": raw.get("stock"),
                    "variants": raw.get("variants", []), "source": raw.get("source", "html")},
        "confirmed_facts": facts,
        "unavailable": missing,
        "selling_angles": selling_angles(facts),
        "video_strategy": {},
    }
    try:  # clipes de ambiente (opcional; nunca derruba o produto)
        from broll import prepare_broll
        brief["broll"] = prepare_broll(brief, cfg, logger, offline=getattr(http, "offline", False) if http else False)
    except Exception as e:
        brief["broll"] = []
        logger.warn("b-roll ignorado", erro=str(e)[:160])
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


def list_products(cfg: dict, logger: Logger, catalog: Path | None = None, offline: bool = False,
                  source: str = "auto") -> list[dict]:
    """Retorna produtos 'crus' (ainda sem baixar imagens). Ordem: catálogo manual → API da loja → páginas HTML.
    source='html' força a leitura das páginas. Se a API falhar, cai automaticamente para o HTML."""
    if catalog:
        return load_catalog(catalog)
    if source in ("auto", "api"):
        try:
            prods = supabase_products(cfg, logger, offline)
            if prods:
                return prods
        except Exception as e:  # qualquer falha da API => plano B (HTML), registrado no log
            logger.warn("API da loja indisponível: usando as páginas HTML", erro=str(e)[:200])
            if source == "api":
                raise PipelineError(f"API da loja indisponível: {e}") from e
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


# ----------------------------------------------------------------------------
# Diagnóstico da loja (rodar no PC que tem acesso ao site)
# ----------------------------------------------------------------------------
def diagnose(cfg: dict, logger: Logger, out_dir: Path) -> Path:
    """Consulta a loja AO VIVO (sem cache) e grava um relatório curto + o HTML bruto, para adaptar o
    leitor ao site real. Não gera vídeo nem baixa mais que 1 imagem."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rep: list[str] = [f"Diagnóstico da loja — {iso()}", f"URL: {cfg['store']['base_url']}{cfg['store']['list_path']}", ""]
    try:  # 1) API da própria loja (fonte preferida)
        api = supabase_products(dict(cfg, store=dict(cfg["store"], cache_ttl_hours=0)), logger)
        if api is None:
            rep.append("API da loja: não configurada (config.store.supabase)")
        else:
            rep.append(f"API da loja: OK — {len(api)} produtos publicados | sem estoque: {sum(1 for p in api if p['stock'] == 0)}")
            for p in api[:3]:
                roles = [m["role"] for m in p["image_meta"].values()]
                facts, _ = build_facts(p)
                rep.append(f"  • {p['name']} | estoque {p['stock']} | {len(p['images'])} fotos {roles} | "
                           f"fatos usáveis {sum(1 for x in facts if x['usable'])}, retidos {sum(1 for x in facts if not x['usable'] and x['kind'] != 'price')}")
    except Exception as e:
        rep.append(f"API da loja: FALHOU ({str(e)[:160]}) — o pipeline usa as páginas HTML como plano B")
    rep.append("")
    http = Http(cfg, logger)
    http.s = dict(http.s, cache_ttl_hours=0)  # sempre ao vivo
    base = cfg["store"]["base_url"].rstrip("/")
    list_url = base + cfg["store"]["list_path"]
    try:
        html = http.get(list_url, ttl_hours=0)
    except PipelineError as e:
        rep.append(f"FALHA ao abrir a página de listagem: {e}")
        p = out_dir / "store-diagnostic.txt"
        p.write_text("\n".join(rep), encoding="utf-8-sig")  # BOM: o PowerShell 5 mostra os acentos corretamente
        return p
    (out_dir / "list.html").write_text(html, encoding="utf-8")
    page = parse_html(html)
    prod_links = sorted({urljoin(list_url, l["href"]).split("#")[0] for l in page.links
                         if PRODUCT_LINK.search(urlparse(urljoin(list_url, l["href"])).path)})
    json_prods = []
    for raw in page.jsonld + page.json_scripts:
        d = _loads(raw)
        if d is not None:
            json_prods += products_from_json(d, list_url)
    rep += [f"Listagem: {len(html):,} caracteres | título: {page.title.strip()[:80]!r}",
            f"  JSON-LD: {len(page.jsonld)} | JSON embutido: {len(page.json_scripts)} | links: {len(page.links)}",
            f"  links que parecem produto: {len(prod_links)} | produtos em JSON da própria listagem: {len(json_prods)}",
            f"  blocos de texto visíveis: {len(page.blocks)}"]
    if not prod_links and not json_prods:
        rep.append("  >> NENHUM produto no HTML: a loja provavelmente é montada pelo navegador (SPA). Envie list.html "
                   "e, se possível, o endereço (Network/Rede do navegador) que devolve os produtos em JSON.")
    try:
        urls = discover_product_urls(http, cfg, logger)
        rep.append(f"Descoberta: {len(urls)} produtos (limite {cfg['store']['max_products']})")
    except PipelineError as e:
        urls = prod_links[:3]
        rep.append(f"Descoberta falhou: {str(e)[:200]}")
    for n, u in enumerate(urls[:3], 1):
        rep += ["", f"--- Produto {n}: {u}"]
        try:
            h = http.get(u, ttl_hours=0)
            (out_dir / f"produto{n}.html").write_text(h, encoding="utf-8")
            raw = extract_product_from_html(h, u)
            facts, missing = build_facts(raw, cfg["brand"].get("show_price", False))
            kinds: dict[str, int] = {}
            for f in facts:
                kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
            rep += [f"nome: {raw['name']!r}", f"descrição: {len(raw['description'])} caracteres",
                    f"imagens encontradas: {len(raw['images'])}", f"fatos: {len(facts)} {kinds}",
                    f"usáveis: {sum(1 for f in facts if f['usable'])} | retidos por risco: {sum(1 for f in facts if f['risk'])}",
                    f"não encontrado na fonte: {missing}"]
            for f in facts[:8]:
                rep.append(f"  [{f['kind']}{' RISCO' if f['risk'] else ''}] {f['text'][:90]}")
            if n == 1 and raw["images"]:
                try:
                    r = http.get(raw["images"][0], binary=True)
                    rep.append(f"imagem 1: {len(r.content) / 1024:.0f} KB | {r.headers.get('content-type')} | {raw['images'][0][:100]}")
                except PipelineError as e:
                    rep.append(f"imagem 1 FALHOU: {e}")
        except PipelineError as e:
            rep.append(f"FALHA: {str(e)[:200]}")
    p = out_dir / "store-diagnostic.txt"
    p.write_text("\n".join(rep), encoding="utf-8-sig")  # BOM: o PowerShell 5 mostra os acentos corretamente
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["discover", "brief", "diagnose"])
    ap.add_argument("target", nargs="?", help="URL do produto ou id (no catálogo)")
    ap.add_argument("--catalog", type=Path)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--source", choices=["auto", "api", "html"], default="auto")
    a = ap.parse_args(argv)
    cfg, log = load_config(), Logger("fetcher")
    try:
        if a.cmd == "diagnose":
            from common import logs_dir
            p = diagnose(cfg, log, logs_dir() / "diagnostico-loja")
            print(p.read_text(encoding="utf-8"))
            print(f"\nRelatório salvo em: {p}\n(HTML bruto na mesma pasta: list.html, produto1.html...)")
            return 0
        raws = list_products(cfg, log, a.catalog, a.offline, a.source)
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
