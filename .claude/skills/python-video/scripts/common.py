"""Utilidades compartilhadas: config, caminhos, logs JSONL e máquina de status.

Nada aqui depende de rede nem de bibliotecas pesadas.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SKILL_DIR / "config" / "config.json"
ARCHETYPES_PATH = SKILL_DIR / "config" / "archetypes.json"
STYLES_PATH = SKILL_DIR / "templates" / "styles.json"

# Status do ciclo de vida de um vídeo (ordem importa).
QUEUED, PROCESSING, RENDERING, VALIDATING, READY, FAILED = (
    "QUEUED", "PROCESSING", "RENDERING", "VALIDATING", "READY", "FAILED")
_ALLOWED = {
    QUEUED: {PROCESSING, FAILED},
    PROCESSING: {RENDERING, FAILED},
    RENDERING: {VALIDATING, FAILED},
    VALIDATING: {READY, FAILED},
    READY: set(),
    FAILED: set(),
}


class PipelineError(Exception):
    """Erro esperado do pipeline (dado ausente, validação reprovada...)."""


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
def load_json(path: Path | str, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        raise PipelineError(f"Arquivo não encontrado: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _json_default(o):
    """numpy (float32, int64...) e Path viram tipos JSON normais."""
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def save_json(path: Path | str, data) -> None:
    """Grava JSON de forma atômica (evita arquivo meio escrito)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    os.replace(tmp, p)


def load_config(overrides: dict | None = None) -> dict:
    cfg = load_json(CONFIG_PATH)
    if overrides:
        _deep_update(cfg, overrides)
    return cfg


def _deep_update(base: dict, new: dict) -> dict:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_archetypes() -> dict:
    return load_json(ARCHETYPES_PATH)["archetypes"]


def load_styles() -> dict:
    return load_json(STYLES_PATH)


def format_spec(cfg: dict, name: str | None = None) -> dict:
    name = name or cfg["format"]
    f = dict(cfg["formats"][name])
    f["name"] = name
    return f


def _resolve(base: Path, value: str) -> Path:
    p = Path(os.path.expanduser(value))
    return p if p.is_absolute() else base / p


def work_dir(cfg: dict) -> Path:
    return _resolve(SKILL_DIR, os.environ.get("ALNA_WORK_DIR", cfg["paths"]["work_dir"]))


def cache_dir(cfg: dict) -> Path:
    return _resolve(SKILL_DIR, os.environ.get("ALNA_CACHE_DIR", cfg["paths"]["cache_dir"]))


def music_dir(cfg: dict) -> Path:
    return _resolve(SKILL_DIR, os.environ.get("ALNA_MUSIC_DIR", cfg["paths"]["music_dir"]))


def fonts_dir(cfg: dict) -> Path:
    return _resolve(SKILL_DIR, os.environ.get("ALNA_FONTS_DIR", cfg["paths"]["fonts_dir"]))


def output_dir(cfg: dict) -> Path:
    """Pasta de destino final. No Windows é a pasta do Google Drive sincronizado;
    ALNA_OUTPUT_DIR sobrescreve (usado em testes e em outras máquinas)."""
    env = os.environ.get("ALNA_OUTPUT_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        return Path(cfg["paths"]["output_dir_windows"])
    return _resolve(SKILL_DIR, cfg["paths"]["output_dir_other"])


def logs_dir() -> Path:
    d = Path(os.environ.get("ALNA_LOGS_DIR", SKILL_DIR / "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ----------------------------------------------------------------------------
# Texto / ids
# ----------------------------------------------------------------------------
def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text or "produto")[:max_len].strip("-") or "produto"


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def iso(ts: dt.datetime | None = None) -> str:
    return (ts or now()).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# Logs
# ----------------------------------------------------------------------------
class Logger:
    """Log JSONL (auditoria) + linha legível em stdout/arquivo diário."""

    def __init__(self, job: str | None = None, extra_file: Path | None = None, echo: bool = True):
        self.job = job
        self.extra_file = Path(extra_file) if extra_file else None
        self.echo = echo

    def event(self, level: str, msg: str, **fields) -> dict:
        rec = {"ts": iso(), "level": level, "job": self.job, "msg": msg}
        rec.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(rec, ensure_ascii=False)
        day = now().strftime("%Y-%m-%d")
        for target in filter(None, [logs_dir() / f"{day}.jsonl", self.extra_file]):
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self.echo:
            extra = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None and k != "trace")
            print(f"[{rec['ts']}] {level:<5} {self.job or '-':<22} {msg} {extra}".rstrip(), file=sys.stderr)
        return rec

    def info(self, msg, **f): return self.event("INFO", msg, **f)
    def warn(self, msg, **f): return self.event("WARN", msg, **f)
    def error(self, msg, **f): return self.event("ERROR", msg, **f)


class JobStatus:
    """Estado de um job em <job_dir>/status.json, com transições validadas.

    Um vídeo só vira READY depois de passar por VALIDATING (quality gate)."""

    def __init__(self, job_dir: Path, job_id: str, logger: Logger | None = None, **meta):
        self.path = Path(job_dir) / "status.json"
        self.log = logger
        data = load_json(self.path, default={}) if self.path.exists() else {}
        if not data:
            data = {"job_id": job_id, "status": QUEUED, "history": [], "meta": meta}
            data["history"].append({"status": QUEUED, "ts": iso()})
            save_json(self.path, data)
        self.data = data

    @property
    def status(self) -> str:
        return self.data["status"]

    def set(self, new: str, **info) -> None:
        if new == self.status:
            return
        if new not in _ALLOWED[self.status]:
            raise PipelineError(f"Transição inválida {self.status} → {new}")
        self.data["status"] = new
        self.data["history"].append({"status": new, "ts": iso(), **info})
        if info:
            self.data.setdefault("meta", {}).update(info)
        save_json(self.path, self.data)
        if self.log:
            self.log.info(f"status → {new}", **info)

    def fail(self, error: str) -> None:
        if self.status in (READY, FAILED):
            return
        self.data["error"] = error
        self.set(FAILED, error=error)


# ----------------------------------------------------------------------------
# ffmpeg / ffprobe
# ----------------------------------------------------------------------------
def which_tool(name: str) -> str:
    exe = shutil.which(name) or shutil.which(name + ".exe")
    if not exe:
        raise PipelineError(
            f"'{name}' não encontrado no PATH. Instale o FFmpeg (Windows: winget install Gyan.FFmpeg) "
            "e reabra o terminal.")
    return exe


def run(cmd: list[str], check: bool = True, capture: bool = True, input_bytes: bytes | None = None,
        timeout: int | None = None) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, input=input_bytes, capture_output=capture, timeout=timeout)
    if check and res.returncode != 0:
        err = (res.stderr or b"").decode("utf-8", "replace")[-1500:]
        raise PipelineError(f"Comando falhou ({res.returncode}): {' '.join(map(str, cmd[:6]))}...\n{err}")
    return res


def ffprobe_json(path: Path | str) -> dict:
    res = run([which_tool("ffprobe"), "-v", "error", "-show_format", "-show_streams",
               "-of", "json", str(path)])
    return json.loads(res.stdout.decode("utf-8"))


# ----------------------------------------------------------------------------
# Retomada após desligamento (trava de execução)
# ----------------------------------------------------------------------------
def boot_time() -> float:
    """Instante (epoch) em que o computador ligou; 0.0 se não der para saber."""
    try:
        if os.name == "nt":
            import ctypes
            return time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000.0
        with open("/proc/uptime") as f:
            return time.time() - float(f.read().split()[0])
    except Exception:
        return 0.0


def pid_alive(pid: int) -> bool:
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259  # STILL_ACTIVE
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False
