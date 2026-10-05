"""doctor: confere se este computador está pronto para gerar os vídeos todo dia.

  python doctor.py            # checagens rápidas (sem gastar nada)
  python doctor.py --smoke    # + gera 1 vídeo de teste completo (≈1 min) com fotos sintéticas
  python doctor.py --offline  # não tenta abrir a loja

Saída: OK / AVISO (funciona, mas vale corrigir) / FALHA (a rotina não vai funcionar). Código de saída 1 se houver FALHA.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import (SKILL_DIR, Logger, PipelineError, cache_dir, fonts_dir, load_config, logs_dir, music_dir, output_dir,
                    work_dir)

ROWS: list[tuple[str, str, str, str]] = []


def add(level: str, name: str, detail: str = "", fix: str = "") -> None:
    ROWS.append((level, name, detail, fix))


def check_python():
    v = sys.version_info
    add("OK" if v >= (3, 10) else "FALHA", "Python", f"{v.major}.{v.minor}.{v.micro} ({sys.executable})",
        "" if v >= (3, 10) else "Instale Python 3.10+ (winget install Python.Python.3.12)")


def check_packages():
    for mod, pip in (("PIL", "Pillow"), ("numpy", "numpy"), ("requests", "requests")):
        try:
            m = importlib.import_module(mod)
            add("OK", f"Biblioteca {pip}", getattr(m, "__version__", ""))
        except Exception:
            add("FALHA", f"Biblioteca {pip}", "não instalada", "pip install -r requirements.txt")


def check_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        exe = shutil.which(tool) or shutil.which(tool + ".exe")
        if not exe:
            add("FALHA", tool, "não está no PATH", "winget install Gyan.FFmpeg e reabra o terminal")
            return
    try:
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        fil = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        ver = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        miss = [n for n, hay in (("libx264", enc), ("aac", enc), ("loudnorm", fil), ("alimiter", fil)) if n not in hay]
        add("OK" if not miss else "FALHA", "FFmpeg", ver[:60] if not miss else f"faltam: {miss}",
            "" if not miss else "Use um build completo do FFmpeg (Gyan.FFmpeg)")
    except Exception as e:
        add("FALHA", "FFmpeg", str(e)[:100])


def check_fonts(cfg):
    try:
        import graphics as g
        path, fam = g.find_font(cfg, fonts_dir(cfg))
        top = cfg["fonts"]["priority"][:7]
        add("OK" if fam in top else "AVISO", "Fonte", f"{fam} ({Path(path).name})",
            "" if fam in top else "Copie Inter-Bold.ttf ou Montserrat-Bold.ttf para a pasta fonts/ (visual melhor)")
    except Exception as e:
        add("FALHA", "Fonte", str(e)[:120], "Coloque um .ttf em fonts/")


def check_dirs(cfg):
    out = output_dir(cfg)
    try:
        out.mkdir(parents=True, exist_ok=True)
        t = out / ".doctor-teste"
        t.write_text("ok")
        t.unlink()
        add("OK", "Pasta de destino (Drive)", str(out))
    except Exception as e:
        add("FALHA", "Pasta de destino (Drive)", f"{out} — {str(e)[:80]}",
            "Abra o Google Drive para computador, confira se o G: existe e o caminho em config.json > paths")
    for name, d in (("work", work_dir(cfg)), ("cache", cache_dir(cfg)), ("logs", logs_dir())):
        try:
            d.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(d).free / 1e9
            add("OK" if free >= 3 else ("AVISO" if free >= 1 else "FALHA"), f"Espaço livre ({name})", f"{free:.1f} GB",
                "" if free >= 3 else "Libere espaço: cada vídeo usa ~0,3 GB de trabalho")
        except Exception as e:
            add("FALHA", f"Pasta {name}", str(e)[:100])


def check_store(cfg, offline):
    if offline:
        add("AVISO", "Loja", "não testada (--offline)")
        return
    try:
        import requests
        url = cfg["store"]["base_url"] + cfg["store"]["list_path"]
        r = requests.get(url, headers={"User-Agent": cfg["store"]["user_agent"]}, timeout=12)
        if r.status_code == 200:
            from product_fetcher import PRODUCT_LINK, parse_html
            from urllib.parse import urljoin, urlparse
            pg = parse_html(r.text)
            n = len({l["href"] for l in pg.links if PRODUCT_LINK.search(urlparse(urljoin(url, l["href"])).path)})
            has_json = bool(pg.jsonld or pg.json_scripts)
            if n or has_json:
                add("OK", "Loja", f"{url} abre; {n} links de produto, JSON embutido: {has_json}")
            else:
                add("AVISO", "Loja", f"{url} abre, mas não vejo produtos no HTML (site montado pelo navegador?)",
                    "Rode: python product_fetcher.py diagnose  e me envie o relatório")
        else:
            add("FALHA", "Loja", f"HTTP {r.status_code} em {url}", "Confira internet/endereço")
    except Exception as e:
        add("FALHA", "Loja", str(e)[:100], "Sem internet ou site fora do ar")


def check_voice(cfg):
    e = cfg["elevenlabs"]
    from localsecrets import eleven_credentials
    k, v = eleven_credentials(cfg)
    lock = SKILL_DIR / "config" / "voice.lock.json"
    if k and v:
        locked = json.loads(lock.read_text())["voice_id"] if lock.exists() else None
        if locked and locked != v:
            add("FALHA", "ElevenLabs", "a voz configurada difere da voz oficial travada", "Mantenha a voz da marca ou apague config/voice.lock.json")
        else:
            add("OK", "ElevenLabs", "chave e voz configuradas" + (" (voz travada)" if locked else " (será travada no 1º uso)"))
    else:
        add("AVISO", "ElevenLabs", ("chave lida, falta o voice_id" if k else "não configurado") + (": vídeos saem SEM narração" if not (k and v) else ""),
            "Crie API\\APIelevenlabs.txt com 2 linhas: api_key=SUA_CHAVE e voice_id=ID_DA_VOZ (ou use setx " + e["api_key_env"] + ")")


def check_music(cfg):
    d = music_dir(cfg)
    files = [p for p in d.rglob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac", ".ogg")] if d.exists() else []
    add("OK" if files else "AVISO", "Músicas licenciadas", f"{len(files)} arquivo(s) em {d}" if files else "nenhuma: usando trilha sintetizada",
        "" if files else "Opcional: coloque faixas licenciadas em music/ (ver music/README.md)")


def check_notify():
    tg = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    from notify import email_settings
    em = email_settings() is not None
    if tg or em:
        add("OK", "Aviso ao terminar", ", ".join(n for n, f in (("Telegram", tg), ("e-mail", em)) if f) + "  (teste: python notify.py test)")
    else:
        add("AVISO", "Aviso ao terminar", "nenhum canal configurado (o resumo fica só em logs/ultimo-resumo.txt)",
            "Configure Telegram ou e-mail: veja o topo de scripts/notify.py")


def check_broll(cfg):
    from localsecrets import PIXABAY_KEY, find_secret_file, read_secret
    b = cfg.get("broll", {})
    names = [b.get("key_file", "APIpixabay")]
    key, origin = read_secret(b.get("key_env", "PIXABAY_API_KEY"), names, PIXABAY_KEY)
    if key:
        add("OK", "Clipes de ambiente (Pixabay)", f"chave lida de: {origin}")
        return
    f = find_secret_file(names)
    if f:
        add("FALHA", "Clipes de ambiente (Pixabay)", f"encontrei o arquivo {f.name}, mas não achei nele uma chave no formato esperado "
            "(números-letras, ex.: 12345678-abcdef...)", "Abra o arquivo no Bloco de Notas e cole só a chave, sem aspas")
    else:
        add("AVISO", "Clipes de ambiente (Pixabay)", "sem chave: os vídeos usam só as fotos",
            "Crie o arquivo APIpixabay (Bloco de Notas) na pasta da skill ou em API\\ com a chave dentro, ou defina PIXABAY_API_KEY")


def check_task():
    name = "ALNA-PythonVideo-Diario"
    if os.name != "nt":
        add("AVISO", "Tarefa agendada", "só verificável no Windows")
        return
    ps = (f"$t=Get-ScheduledTask -TaskName '{name}' -ErrorAction Stop; $i=$t | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{state=[string]$t.State; next=$(if($i.NextRunTime){$i.NextRunTime.ToString('yyyy-MM-dd HH:mm')}); "
          "last=$(if($i.LastRunTime){$i.LastRunTime.ToString('yyyy-MM-dd HH:mm')}); result=$i.LastTaskResult} | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        add("FALHA", "Tarefa agendada", f"'{name}' não existe", "python scheduler.py install-task")
        return
    try:
        info = json.loads(r.stdout.strip())
    except Exception:
        add("OK", "Tarefa agendada", "registrada (não consegui ler os detalhes)")
        return
    res = info.get("result")
    meaning = {0: "sucesso", 267011: "ainda não rodou", 267009: "rodando agora", 267014: "interrompida"}.get(res, f"código {res}")
    nxt = info.get("next") or "—"
    ok = info.get("state") in ("Ready", "Running") and nxt != "—"
    add("OK" if ok else "AVISO", "Tarefa agendada", f"estado {info.get('state')}; próxima execução: {nxt}; última: {info.get('last') or '—'} ({meaning})",
        "" if ok else "Se estiver Disabled: Enable-ScheduledTask -TaskName " + name)


def check_last_runs(cfg):
    """Fonte de verdade = estado por vídeo (work/state.json), não o resumo da execução (que pode ser de uma rodada sem nada a fazer)."""
    from common import work_dir
    target = cfg["daily"]["videos"]
    st = work_dir(cfg) / "state.json"
    if st.exists():
        days = json.loads(st.read_text(encoding="utf-8")).get("days", {})
        if days:
            day = max(days)
            slots = days[day].get("slots", {})
            done = [s for s in slots.values() if s.get("status") == "READY" and s.get("delivered")]
            pend = [s for s in slots.values() if s.get("status") == "READY" and not s.get("delivered")]
            age = (dt.date.today() - dt.date.fromisoformat(day)).days
            names = ", ".join(s.get("final_name", "?") for s in done)
            ok = len(done) >= target and age <= 1
            detail = f"{day}: {len(done)}/{target} vídeos prontos e entregues" + (f" ({names})" if names else "")
            if pend:
                detail += f"; {len(pend)} pronto(s) aguardando cópia para a pasta final"
            add("OK" if ok else "AVISO", "Última rotina", detail,
                "" if ok else "Veja logs\\daily-*.json e o arquivo .jsonl do dia; a pasta do dia no Drive mostra o que existe")
            return
    files = sorted(logs_dir().glob("daily-*.json"))
    if not files:
        add("AVISO", "Última rotina", "ainda não rodou")
        return
    d = json.loads(files[-1].read_text(encoding="utf-8"))
    age = (dt.date.today() - dt.date.fromisoformat(d["day"])).days
    ok = d.get("ready", 0) >= d.get("target", 3)
    add("OK" if ok and age <= 1 else "AVISO", "Última rotina", f"{d['day']}: {d.get('ready', 0)}/{d.get('target', 3)} vídeos"
        + (" (atrasada)" if d.get("late") else ""), "" if ok and age <= 1 else "Veja logs/daily-*.json e o arquivo .jsonl do dia")


def smoke(cfg):
    """Gera 1 vídeo completo com fotos sintéticas (não usa a loja nem a internet)."""
    sys.path.insert(0, str(SKILL_DIR / "tests"))
    from fixtures import make_catalog
    import product_fetcher as pf
    from build_video import build_video
    tmp = Path(tempfile.mkdtemp(prefix="pyvideo-smoke-"))
    os.environ.update({"ALNA_WORK_DIR": str(tmp / "work"), "ALNA_CACHE_DIR": str(tmp / "cache")})
    try:
        log = Logger("smoke", echo=False)
        raw = pf.load_catalog(make_catalog(tmp / "fx"))[0]
        brief = pf.get_brief(raw, cfg, log)
        res = build_video(brief, cfg, "smoke", day="smoke", seed=1, voice_mode="off", deliver_output=False)
        add("OK", "Teste completo (vídeo de verdade)", f"READY em {res['duration']}s, {len(res.get('warnings', []))} avisos")
    except Exception as e:
        add("FALHA", "Teste completo (vídeo de verdade)", str(e)[:200], "Veja a mensagem; rode python tests/test_pipeline.py --fast")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    check_python(); check_packages(); check_ffmpeg(); check_fonts(cfg); check_dirs(cfg)
    check_store(cfg, a.offline); check_voice(cfg); check_music(cfg); check_notify(); check_broll(cfg); check_task(); check_last_runs(cfg)
    if a.smoke and not any(r[0] == "FALHA" and r[1] in ("FFmpeg", "ffmpeg", "ffprobe", "Fonte") for r in ROWS):
        smoke(cfg)
    icons = {"OK": "OK   ", "AVISO": "AVISO", "FALHA": "FALHA"}
    for lvl, name, detail, fix in ROWS:
        print(f"[{icons[lvl]}] {name}: {detail}")
        if fix and lvl != "OK":
            print(f"        → {fix}")
    n_fail = sum(1 for r in ROWS if r[0] == "FALHA")
    n_warn = sum(1 for r in ROWS if r[0] == "AVISO")
    print(f"\nResultado: {'PRONTO' if not n_fail else 'NÃO PRONTO'} — {n_fail} falha(s), {n_warn} aviso(s)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
