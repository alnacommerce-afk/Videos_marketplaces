"""Leitura de segredos (chaves de API) fora do repositório.

Ordem: variável de ambiente → arquivo local na pasta da skill ou na subpasta `API\\` (ex.: `APIpixabay`, `API\\APIpixabay.txt`).
O arquivo é só do seu computador: está no .gitignore e nenhum teste/código o copia, loga ou empacota.
(O nome não pode ser `secrets.py`: esse nome é um módulo da biblioteca padrão do Python.)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from common import SKILL_DIR

PIXABAY_KEY = r"\b\d{6,}-[0-9a-f]{20,}\b"


def _read_text(path: Path) -> str:
    """O Bloco de Notas pode salvar em UTF-8 (com/sem BOM), UTF-16 ou ANSI."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("latin-1")


def _extract(text: str, pattern: str | None) -> str | None:
    if pattern:  # aceita "chave: XXXX", "key=XXXX", comentários, linhas extras...
        m = re.search(pattern, text, re.I)
        return m.group(0) if m else None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return re.split(r"\s*[=:]\s*", line, maxsplit=1)[-1].strip().strip("\"'") or None
    return None


def find_secret_file(file_names: list[str], base: Path | None = None) -> Path | None:
    """Primeiro arquivo existente entre os nomes (com/sem a extensão .txt escondida pelo Windows)."""
    base = base or SKILL_DIR
    for name in file_names:
        # na pasta da skill e na subpasta API\ (onde o dono guarda as chaves)
        dirs = [None] if Path(name).is_absolute() else [base, base / "API"]
        for d in dirs:
            if d is not None and "*" in name:  # nome com curinga (ex.: *eleven*): primeiro arquivo que combina
                hits = sorted(x for x in d.glob(name) if x.is_file()) if d.is_dir() else []
                if hits:
                    return hits[0]
                continue
            p = Path(name) if d is None else d / name
            for suffix in ("", ".txt", ".txt.txt"):
                cand = p.with_name(p.name + suffix)
                if cand.is_file():
                    return cand
    return None


def read_secret(env_name: str, file_names: list[str], pattern: str | None = None,
                base: Path | None = None) -> tuple[str | None, str]:
    """Retorna (valor, origem). `origem` descreve de onde veio (nunca o valor)."""
    v = os.environ.get(env_name, "").strip()
    if v:
        return v, f"variável {env_name}"
    f = find_secret_file(file_names, base)
    if f:
        val = _extract(_read_text(f), pattern)
        if val:
            return val, f"arquivo {f.name}"
    return None, ""


def read_kv(file_names: list[str], base: Path | None = None) -> dict[str, str]:
    """Lê um arquivo local de linhas `chave=valor` / `chave: valor` (# comenta). Ex.: APIemail com host/user/password/to."""
    f = find_secret_file(file_names, base)
    out: dict[str, str] = {}
    if not f:
        return out
    for line in _read_text(f).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or not re.search(r"[=:]", line):
            continue
        k, v = re.split(r"\s*[=:]\s*", line, maxsplit=1)
        out[re.sub(r"[\s_-]+", "_", k.strip().lower())] = v.strip().strip("\"'")
    return out


ELEVEN_KEY = r"\bsk_[A-Za-z0-9]{20,}\b"
ELEVEN_FILES = ["APIelevenlabs", "ElevenLabs", "*eleven*"]


def eleven_credentials(cfg: dict, base: Path | None = None) -> tuple[str | None, str | None]:
    """(chave, voice_id) do ElevenLabs: variável de ambiente ou arquivo local em API\\ (chave sozinha na linha, ou
    `api_key=...` / `voice_id=...`). Nunca loga o valor."""
    e = cfg["elevenlabs"]
    key, _ = read_secret(e["api_key_env"], ELEVEN_FILES, ELEVEN_KEY, base=base)
    kv = read_kv(ELEVEN_FILES, base)
    if not key:
        key = kv.get("api_key") or kv.get("key") or kv.get("xi_api_key")
    if not key:  # arquivo só com a chave, sem rótulo
        f = find_secret_file(ELEVEN_FILES, base)
        if f:
            key = _extract(_read_text(f), None)
            if key and re.search(r"[=:\s]", key):
                key = None
    vid = os.environ.get(e["voice_id_env"], "").strip() or kv.get("voice_id") or kv.get("voice") or None
    return key, vid


HEYGEN_FILES = ["APIheygen", "HeyGen", "*heygen*"]


def heygen_credentials(base: Path | None = None) -> dict:
    """{key, avatar_id, voice_id} do HeyGen: variável HEYGEN_API_KEY ou arquivo em API\\ (`api_key=...`, ou só a chave numa linha).
    avatar_id/voice_id não são segredos: podem estar no mesmo arquivo (`avatar_id=`, `voice_id=`) ou em config/presenter.lock.json."""
    kv = read_kv(HEYGEN_FILES, base)
    key = os.environ.get("HEYGEN_API_KEY", "").strip() or kv.get("api_key") or kv.get("key") or kv.get("x_api_key")
    if not key:
        f = find_secret_file(HEYGEN_FILES, base)
        if f:
            key = _extract(_read_text(f), None)
            if key and re.search(r"[=:\s]", key):
                key = None
    return {"key": key, "avatar_id": os.environ.get("HEYGEN_AVATAR_ID") or kv.get("avatar_id"),
            "voice_id": os.environ.get("HEYGEN_VOICE_ID") or kv.get("voice_id")}
