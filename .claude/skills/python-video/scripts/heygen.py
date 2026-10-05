"""Embaixadora da marca em vídeo (HeyGen) — FASE 2, opcional e desligada por padrão (`presenter.enabled`).

Uso: só a ABERTURA do vídeo (3–5 s), com roteiro NOSSO e rastreável (pergunta-gancho com o nome do produto, ou um fato de uso
confirmado). Nunca o Video Agent (ele escreve o próprio roteiro); nunca criança gerada por IA.

Fluxo da API v3 (docs.heygen.com): POST /v3/assets (envia a foto) -> POST /v3/avatars {type: photo} -> POST /v3/videos
{type: avatar, avatar_id, script, voice_id} -> GET /v3/videos/{id} até `completed` -> baixar `video_url`.
Chave: variável HEYGEN_API_KEY ou arquivo local API\\APIheygen.txt (nunca no repositório). Cada vídeo gasta crédito do HeyGen:
há cache por roteiro e um teto diário (`presenter.max_new_videos_per_day`).

  python heygen.py avatar --photo C:\\ALNA\\python-video\\embaixadora\\embaixadora.png --confirm-consent
  python heygen.py intro --text "Já conhece a Toalha de Capivara?" [--dry-run]
  python heygen.py status
O --confirm-consent declara que a pessoa da foto autorizou o uso da imagem em avatar de IA (ou que é um personagem sintético).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from common import (CONFIG_PATH, Logger, PipelineError, cache_dir, ffprobe_json, iso, load_config, load_json, redact, save_json)
from localsecrets import heygen_credentials

LOCK = CONFIG_PATH.parent / "presenter.lock.json"


class HeyGenError(PipelineError):
    pass


def _pick(d: dict, *names):
    """Os ids podem vir como data.id, data.video_id, data.avatar_id...: pega o primeiro que existir."""
    for n in names:
        if isinstance(d, dict) and d.get(n):
            return d[n]
    return None


def load_lock() -> dict:
    return load_json(LOCK, {}) or {}


class HeyGen:
    def __init__(self, cfg: dict, logger: Logger | None = None, base: Path | None = None):
        self.cfg, self.log = cfg, logger or Logger("heygen", echo=False)
        self.p = cfg.get("presenter", {})
        self.base_url = self.p.get("api_base", "https://api.heygen.com").rstrip("/")
        cred = heygen_credentials(base)
        lock = load_lock()
        self.key = cred["key"]
        self.avatar_id = lock.get("avatar_id") or cred["avatar_id"]
        self.voice_id = lock.get("voice_id") or cred["voice_id"] or self.p.get("voice_id")

    def ready(self) -> bool:
        return bool(self.key and self.avatar_id and self.voice_id)

    def _req(self, method: str, path: str, **kw) -> dict:
        try:
            r = requests.request(method, self.base_url + path, headers={"X-Api-Key": self.key}, timeout=kw.pop("timeout", 60), **kw)
        except requests.RequestException as e:
            raise HeyGenError(redact(f"HeyGen inacessível: {e}")) from e
        if r.status_code >= 400:
            raise HeyGenError(redact(f"HeyGen {method} {path}: HTTP {r.status_code} {r.text[:300]}"))
        try:
            body = r.json()
        except ValueError as e:
            raise HeyGenError(f"HeyGen {path}: resposta sem JSON") from e
        return body.get("data", body) if isinstance(body, dict) else {}

    # ---- avatar a partir da foto -------------------------------------------------
    def upload_asset(self, photo: Path) -> str:
        with open(photo, "rb") as fh:
            d = self._req("POST", "/v3/assets", files={"file": (photo.name, fh, "image/png" if photo.suffix.lower() == ".png" else "image/jpeg")}, timeout=180)
        aid = _pick(d, "asset_id", "id")
        if not aid:
            raise HeyGenError(f"HeyGen não devolveu o id do arquivo enviado: {str(d)[:200]}")
        return aid

    def create_photo_avatar(self, asset_id: str, name: str) -> str:
        d = self._req("POST", "/v3/avatars", json={"type": "photo", "name": name, "asset_id": asset_id})
        avid = _pick(d, "avatar_id", "id", "avatar_item_id")
        if not avid:
            raise HeyGenError(f"HeyGen não devolveu o id do avatar: {str(d)[:200]}")
        return avid

    # ---- vídeo -------------------------------------------------------------------
    def video_payload(self, script: str, title: str) -> dict:
        return {"type": "avatar", "avatar_id": self.avatar_id, "voice_id": self.voice_id, "script": script, "title": title,
                "resolution": self.p.get("resolution", "1080p"), "aspect_ratio": self.p.get("aspect_ratio", "9:16")}

    def create_video(self, script: str, title: str) -> str:
        d = self._req("POST", "/v3/videos", json=self.video_payload(script, title))
        vid = _pick(d, "video_id", "id")
        if not vid:
            raise HeyGenError(f"HeyGen não devolveu o id do vídeo: {str(d)[:200]}")
        return vid

    def wait_video(self, vid: str) -> dict:
        deadline = time.time() + self.p.get("timeout_s", 900)
        every = self.p.get("poll_s", 8)
        while time.time() < deadline:
            d = self._req("GET", f"/v3/videos/{vid}")
            st = (d.get("status") or "").lower()
            if st == "completed" and d.get("video_url"):
                return d
            if st == "failed":
                raise HeyGenError(f"HeyGen falhou ao gerar o vídeo: {d.get('failure_code')} {d.get('failure_message')}")
            time.sleep(every)
        raise HeyGenError("HeyGen demorou demais para gerar o vídeo")

    def download(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=180)
        r.raise_for_status()
        dest.write_bytes(r.content)
        info = ffprobe_json(str(dest))
        if not any(s["codec_type"] == "video" for s in info["streams"]):
            dest.unlink(missing_ok=True)
            raise HeyGenError("vídeo baixado do HeyGen sem stream de vídeo")
        return dest


def _daily_count(cfg: dict) -> tuple[Path, dict]:
    f = cache_dir(cfg) / "heygen" / "uso.json"
    data = load_json(f, {}) or {}
    today = time.strftime("%Y-%m-%d")
    return f, ({today: data.get(today, 0)} if data else {today: 0})


def generate_intro(script: str, cfg: dict, logger: Logger, base: Path | None = None) -> dict:
    """Gera (ou reaproveita do cache) o clipe da embaixadora falando `script`. Devolve {path, duration, video_id, ...}."""
    hg = HeyGen(cfg, logger, base)
    if not hg.ready():
        raise HeyGenError("HeyGen não configurado: faltam chave, avatar_id ou voice_id (veja SKILL.md)")
    key = hashlib.sha1(json.dumps([script, hg.avatar_id, hg.voice_id, hg.p.get("aspect_ratio"), hg.p.get("resolution")]).encode()).hexdigest()[:20]
    out = cache_dir(cfg) / "heygen" / f"intro-{key}.mp4"
    meta = out.with_suffix(".json")
    if out.exists() and meta.exists():
        return load_json(meta)
    usage_file, usage = _daily_count(cfg)
    today = next(iter(usage))
    if usage[today] >= hg.p.get("max_new_videos_per_day", 3):
        raise HeyGenError("teto diário de vídeos novos do HeyGen atingido (presenter.max_new_videos_per_day)")
    vid = hg.create_video(script, f"ALNA intro {key}")
    logger.info("HeyGen: vídeo em geração", video_id=vid)
    done = hg.wait_video(vid)
    hg.download(done["video_url"], out)
    usage[today] += 1
    save_json(usage_file, usage)
    dur = float(ffprobe_json(str(out))["format"].get("duration", 0))
    res = {"path": str(out), "duration": round(dur, 3), "video_id": vid, "avatar_id": hg.avatar_id, "script": script, "created_at": iso()}
    save_json(meta, res)
    return res


def presenter_script(brief: dict, cfg: dict) -> tuple[str, str] | None:
    """(fonte rastreável, texto exibido) da fala da embaixadora: a pergunta-gancho com o nome do produto (nome curto) ou um fato de
    USO confirmado. Nunca texto livre; nunca chamada para fora (marketplace)."""
    from storyboard import expected_text, is_external
    max_words = cfg.get("presenter", {}).get("max_words", 12)
    if len(brief["product"]["name"]) <= 38:
        t = expected_text("template:question", brief, cfg)
        if t and len(t.split()) <= max_words and not is_external(t):
            return "template:question", t
    for f in brief["confirmed_facts"]:
        if f["usable"] and f["kind"] == "use" and f["display"] and len(f["display"].split()) <= max_words and not is_external(f["display"]):
            return f"fact:{f['id']}", f["display"]
    return None


def prepare_presenter(brief: dict, cfg: dict, logger: Logger, base: Path | None = None) -> dict | None:
    """Abertura da embaixadora para este produto, ou None (desligado, sem avatar/voz, sem roteiro, erro). Nunca derruba o vídeo."""
    p = cfg.get("presenter") or {}
    if not p.get("enabled"):
        return None
    try:
        sc = presenter_script(brief, cfg)
        if not sc:
            logger.info("embaixadora: sem roteiro rastreável para este produto")
            return None
        from audio import speakable
        res = generate_intro(speakable(sc[1]), cfg, logger, base)
        if res["duration"] > p.get("intro_max_s", 5.0):
            logger.warn("embaixadora: abertura longa demais, ignorada", duracao=res["duration"])
            return None
        return {**res, "source": sc[0], "text": sc[1]}
    except Exception as e:  # opcional
        logger.warn("embaixadora indisponível: o vídeo segue sem ela", erro=redact(str(e))[:200])
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Embaixadora da marca (HeyGen)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("avatar", help="cria o avatar a partir da foto da embaixadora e trava o id")
    a1.add_argument("--photo", type=Path, required=True)
    a1.add_argument("--name", default="Embaixadora ALNA")
    a1.add_argument("--voice-id", help="voice_id do HeyGen a usar (ou deixe em API\\APIheygen.txt)")
    a1.add_argument("--confirm-consent", action="store_true", help="declaro que a pessoa da foto autorizou o uso da imagem em avatar de IA (ou é personagem sintético)")
    a2 = sub.add_parser("intro", help="gera uma abertura de teste")
    a2.add_argument("--text", required=True)
    a2.add_argument("--dry-run", action="store_true", help="só mostra o que seria enviado (não gasta crédito)")
    sub.add_parser("status", help="mostra o que está configurado (sem mostrar a chave)")
    a = ap.parse_args(argv)
    cfg, log = load_config(), Logger("heygen")
    hg = HeyGen(cfg, log)
    try:
        if a.cmd == "status":
            print(json.dumps({"chave": bool(hg.key), "avatar_id": hg.avatar_id, "voice_id": hg.voice_id, "pronto": hg.ready(),
                              "habilitado_na_config": bool(cfg.get("presenter", {}).get("enabled"))}, ensure_ascii=False, indent=2))
            return 0
        if not hg.key:
            raise HeyGenError("sem chave: crie API\\APIheygen.txt com a chave (ou defina HEYGEN_API_KEY)")
        if a.cmd == "avatar":
            if not a.confirm_consent:
                raise HeyGenError("confirme a autorização da imagem com --confirm-consent (a pessoa da foto autorizou avatar de IA, ou é personagem sintético)")
            aid = hg.upload_asset(a.photo)
            avid = hg.create_photo_avatar(aid, a.name)
            lock = load_lock()
            lock.update({"avatar_id": avid, "created_at": iso(), "consent_confirmed": True})
            if a.voice_id:
                lock["voice_id"] = a.voice_id
            save_json(LOCK, lock)
            print(f"Avatar criado e travado em {LOCK.name}: {avid}")
            return 0
        if a.cmd == "intro":
            if a.dry_run:
                print(json.dumps({k: v for k, v in hg.video_payload(a.text, "teste").items()}, ensure_ascii=False, indent=2))
                return 0
            res = generate_intro(a.text, cfg, log)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
    except PipelineError as e:
        log.error(str(e)[:400])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
