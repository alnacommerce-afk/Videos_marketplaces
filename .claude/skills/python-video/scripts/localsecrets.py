"""Leitura de segredos (chaves de API) fora do repositório.

Ordem: variável de ambiente → arquivo local na pasta da skill (ex.: `APIpixabay`, `APIpixabay.txt`).
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
        p = Path(name) if Path(name).is_absolute() else base / name
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
