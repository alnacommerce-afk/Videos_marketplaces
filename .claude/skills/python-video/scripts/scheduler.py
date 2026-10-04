"""Rotina diária: 3 vídeos por madrugada, prontos antes das 08:00.

NÃO é um loop infinito: o Windows Task Scheduler dispara `scheduler.py run-daily` às 02:00 (e uma
execução de recuperação às 05:00). Cada execução é idempotente: só produz os vídeos que ainda faltam
no dia, então rodar duas vezes não gera 6 vídeos.

Comandos:
  run-daily     produz os vídeos que faltam hoje
  install-task  cria a tarefa no Task Scheduler (Windows) / gera o XML (outros SO)
  status        mostra o estado do dia
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
import time
import zlib
from pathlib import Path
from xml.sax.saxutils import escape

import product_fetcher as pf
from build_video import build_video, deliver
from common import (SKILL_DIR, Logger, PipelineError, boot_time, cache_dir, iso, pid_alive, load_archetypes, load_config, load_json,
                    logs_dir, output_dir, save_json, slugify, work_dir)
from storyboard import eligible_archetypes

TASK_NAME = "ALNA-PythonVideo-Diario"


# ----------------------------------------------------------------------------
# Estado + lock
# ----------------------------------------------------------------------------
def state_path(cfg: dict) -> Path:
    return work_dir(cfg) / "state.json"


def load_state(cfg: dict) -> dict:
    return load_json(state_path(cfg), default={}) if state_path(cfg).exists() else {"products": {}, "recent_archetypes": [], "days": {}}


class Lock:
    """Impede duas execuções simultâneas (o Task Scheduler também usa IgnoreNew; isto cobre execução manual).

    A trava é considerada ABANDONADA (e assumida) quando: o processo dono não existe mais, ou ela foi criada
    antes do último boot do computador (queda de energia / reinício), ou tem mais de `stale_hours`. Assim,
    se o PC desligar no meio da rotina, a próxima execução retoma sem esperar horas."""

    def __init__(self, cfg: dict, stale_hours: float = 6.0):
        self.path = work_dir(cfg) / "daily.lock"
        self.stale = stale_hours * 3600

    def _abandoned(self) -> str | None:
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return "arquivo de trava ilegível"
        mtime = self.path.stat().st_mtime
        if mtime < boot_time() - 5:
            return "criada antes do último boot do computador"
        if not pid_alive(info.get("pid", -1)):
            return f"processo {info.get('pid')} não existe mais"
        if time.time() - mtime > self.stale:
            return "mais de 6 h sem atualização"
        return None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            why = self._abandoned()
            if why is None:
                raise PipelineError(f"Já existe uma execução em andamento ({self.path}). Se for engano, apague o arquivo.")
            Logger("lock").warn("trava abandonada: assumindo a execução", motivo=why)
        self.path.write_text(json.dumps({"pid": os.getpid(), "since": iso()}), encoding="utf-8")
        return self

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)


def parse_hhmm(s: str, ref: dt.datetime) -> dt.datetime:
    h, m = map(int, s.split(":"))
    return ref.replace(hour=h, minute=m, second=0, microsecond=0)


# ----------------------------------------------------------------------------
# Seleção
# ----------------------------------------------------------------------------
def rank_products(raws: list[dict], state: dict, day: str, cooldown: int, rng: random.Random) -> list[dict]:
    """Prefere produtos nunca usados / usados há mais tempo; respeita o cooldown quando há alternativa."""
    today = dt.date.fromisoformat(day)
    scored = []
    for r in raws:
        if not r.get("images") or not r.get("name"):
            continue
        pid = slugify(r.get("id") or r.get("url", "").rstrip("/").split("/")[-1] or r["name"], 60)
        last = state["products"].get(pid, {}).get("last_date")
        age = (today - dt.date.fromisoformat(last)).days if last else 999
        scored.append((age, rng.random(), pid, r))
    fresh = [s for s in scored if s[0] >= cooldown]
    pool = fresh if fresh else scored
    pool.sort(key=lambda s: (-s[0], s[1]))
    rest = [s for s in sorted(scored, key=lambda s: (-s[0], s[1])) if s not in pool]
    return [s[3] for s in pool + rest]


def run_daily(cfg: dict | None = None, day: str | None = None, count: int | None = None, catalog: Path | None = None,
              voice_mode: str = "auto", now_fn=dt.datetime.now, offline: bool = False, out_root: Path | None = None,
              build_fn=build_video) -> dict:
    cfg = cfg or load_config()
    dcfg = cfg["daily"]
    count = count or dcfg["videos"]
    now = now_fn()
    day = day or now.date().isoformat()
    log = Logger(f"daily-{day}")
    deadline = parse_hhmm(dcfg["deadline"], now)
    out_root = out_root or output_dir(cfg)
    summary = {"day": day, "started_at": iso(), "target": count, "videos": [], "skipped": [], "errors": []}
    with Lock(cfg):
        state = load_state(cfg)
        dayst = state["days"].setdefault(day, {"slots": {}})
        for part in (out_root / day).glob("*.partial") if (out_root / day).exists() else []:
            part.unlink(missing_ok=True)  # sobra de uma cópia interrompida por desligamento
            log.warn("cópia incompleta removida", arquivo=part.name)
        # 1) entrega pendente: vídeo READY cuja cópia para a pasta final falhou antes (ex.: Drive offline)
        for slot, s in dayst["slots"].items():
            if s.get("status") == "READY" and not s.get("delivered"):
                try:
                    jd = Path(s["job_dir"])
                    s["final_path"] = str(deliver(jd, s["final_name"], out_root, day, log))
                    s["delivered"] = True
                    log.info("entrega pendente concluída", slot=slot)
                except Exception as e:
                    log.warn("entrega pendente ainda falhando", slot=slot, erro=str(e)[:200])
        done = {int(k) for k, s in dayst["slots"].items() if s.get("status") == "READY" and s.get("delivered")}
        todo = [i for i in range(1, count + 1) if i not in done]
        log.info("início da rotina", dia=day, prontos=len(done), faltam=len(todo))
        if not todo:
            summary["note"] = "todos os vídeos do dia já estavam prontos"
            save_state(cfg, state)
            return _finish(cfg, summary, log)

        # 2) catálogo (com cópia local para o caso de a loja estar fora do ar)
        snap = cache_dir(cfg) / "catalog_snapshot.json"
        try:
            raws = pf.list_products(cfg, log, catalog, offline)
            save_json(snap, raws)
        except PipelineError as e:
            log.error("falha ao ler a loja", erro=str(e)[:300])
            if snap.exists():
                raws = load_json(snap)
                log.warn("usando a última lista de produtos salva", produtos=len(raws))
            else:
                summary["errors"].append(f"catálogo indisponível: {e}")
                return _finish(cfg, summary, log, state)
        rng = random.Random(day)
        ranked = rank_products(raws, state, day, dcfg["cooldown_days"], rng)
        if len(ranked) < len(todo):
            log.warn("produtos insuficientes: não vou inventar conteúdo", disponiveis=len(ranked), necessarios=len(todo))
        used_today = {s["product_id"] for s in dayst["slots"].values() if s.get("status") == "READY"}
        used_arch = [s["archetype"] for s in dayst["slots"].values() if s.get("status") == "READY"]
        used_music = [s["music"] for s in dayst["slots"].values() if s.get("status") == "READY"]
        used_hook = [s["hook"] for s in dayst["slots"].values() if s.get("status") == "READY"]
        cursor = 0
        archetypes = load_archetypes()

        for slot in todo:
            if now_fn() >= deadline:
                if not dcfg.get("catch_up_after_deadline", True):
                    log.warn("prazo das 08:00 atingido: não inicio novos vídeos", slot=slot)
                    summary["skipped"].append({"slot": slot, "motivo": "prazo"})
                    continue
                if not summary.get("late"):
                    summary["late"] = True
                    log.warn("passou das 08:00: produzindo os vídeos que faltam do dia mesmo assim (retomada)")
            ok = False
            while cursor < len(ranked) and not ok:
                raw = ranked[cursor]
                cursor += 1
                pid = slugify(raw.get("id") or raw.get("url", "").rstrip("/").split("/")[-1] or raw["name"], 60)
                if pid in used_today:
                    continue
                try:
                    brief = pf.get_brief(raw, cfg, log, offline=offline)
                except PipelineError as e:
                    log.warn("produto descartado", produto=raw["name"], motivo=str(e)[:200])
                    summary["errors"].append({"produto": raw["name"], "erro": str(e)[:200]})
                    continue
                if len([f for f in brief["confirmed_facts"] if f["usable"] and f["kind"] != "price"]) < dcfg["min_facts"]:
                    log.warn("produto sem fatos confirmados suficientes: pulado", produto=raw["name"])
                    summary["skipped"].append({"produto": raw["name"], "motivo": "poucos fatos confirmados"})
                    continue
                last_arch = state["products"].get(pid, {}).get("archetypes", [])
                tried: list[str] = []
                for attempt in range(1, dcfg["max_attempts_per_slot"] + 1):
                    if now_fn() >= deadline and not dcfg.get("catch_up_after_deadline", True):
                        break
                    job_id = f"{day}-s{slot}-{slugify(brief['product']['name'], 20)}-a{attempt}"
                    # a cada tentativa, outro arquétipo (se falhou, a estratégia pode ser o problema)
                    try:
                        from storyboard import choose_archetype
                        arch = choose_archetype(brief, random.Random(f"{day}{slot}{attempt}"),
                                                avoid_archetypes=used_arch + last_arch[-2:] + tried,
                                                recent=state["recent_archetypes"][-6:], archetypes=archetypes)
                    except PipelineError as e:
                        log.warn("sem arquétipo elegível", produto=raw["name"], motivo=str(e))
                        break
                    tried.append(arch)
                    try:
                        res = build_fn(brief, cfg, job_id, day=day, archetype=arch, seed=zlib.crc32(f"{day}|{slot}|{attempt}".encode()) & 0xFFFF,
                                       voice_mode=voice_mode, music_avoid=used_music, hook_avoid=used_hook,
                                       out_root=out_root, slot=slot)
                    except PipelineError as e:
                        log.warn("tentativa falhou", slot=slot, tentativa=attempt, arquetipo=arch, erro=str(e)[:200])
                        summary["errors"].append({"slot": slot, "tentativa": attempt, "produto": raw["name"], "erro": str(e)[:300]})
                        continue
                    sbj = load_json(work_dir(cfg) / day / job_id / "storyboard.json")
                    entry = {"status": "READY", "delivered": bool(res.get("final_path")), "product_id": pid, "job_dir": str(work_dir(cfg) / day / job_id),
                             "final_name": res["final_name"], "final_path": res.get("final_path"), "archetype": arch,
                             "music": sbj["strategy"]["music_profile"], "hook": sbj["strategy"]["hook_style"]}
                    dayst["slots"][str(slot)] = entry
                    p = state["products"].setdefault(pid, {"archetypes": []})
                    p["last_date"] = day
                    p["archetypes"] = (p["archetypes"] + [arch])[-6:]
                    state["recent_archetypes"] = (state["recent_archetypes"] + [arch])[-12:]
                    used_today.add(pid)
                    used_arch.append(arch)
                    used_music.append(entry["music"])
                    used_hook.append(entry["hook"])
                    summary["videos"].append({"slot": slot, "produto": raw["name"], "arquetipo": arch, "arquivo": res.get("final_path")})
                    save_state(cfg, state)
                    ok = True
                    break
            if not ok:
                log.error("não consegui produzir o vídeo deste slot", slot=slot)
                summary["skipped"].append({"slot": slot, "motivo": "sem produto/estratégia válidos"})
        return _finish(cfg, summary, log, state)


def save_state(cfg: dict, state: dict) -> None:
    save_json(state_path(cfg), state)


def _finish(cfg: dict, summary: dict, log: Logger, state: dict | None = None) -> dict:
    if state is not None:
        save_state(cfg, state)
    summary["finished_at"] = iso()
    summary["ready"] = len(summary["videos"])
    summary["exit_code"] = 0 if summary["ready"] >= summary["target"] or summary.get("note") else (2 if summary["videos"] else 1)
    save_json(logs_dir() / f"daily-{summary['day']}.json", summary)
    log.info("rotina finalizada", prontos=summary["ready"], meta=summary["target"])
    if not summary.get("note"):  # não avisa de novo quando só confirmou que o dia já estava completo
        from notify import notify_daily
        notify_daily(summary, log)
    return summary


# ----------------------------------------------------------------------------
# Windows Task Scheduler
# ----------------------------------------------------------------------------
def task_xml(python_exe: str, cfg: dict, start: str, recovery: str) -> str:
    first = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    script = str(SKILL_DIR / "scripts" / "scheduler.py")

    def trig(hhmm):
        return (f"<CalendarTrigger><StartBoundary>{first}T{hhmm}:00</StartBoundary><Enabled>true</Enabled>"
                f"<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>ALNA: gera os vídeos comerciais do dia (python-video) e salva no Google Drive antes das 08:00.</Description></RegistrationInfo>
  <Triggers>{trig(start)}{trig(recovery)}</Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT5H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT10M</Interval><Count>3</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec>
    <Command>{escape(python_exe)}</Command>
    <Arguments>"{escape(script)}" run-daily</Arguments>
    <WorkingDirectory>{escape(str(SKILL_DIR / "scripts"))}</WorkingDirectory>
  </Exec></Actions>
</Task>
"""


def install_task(cfg: dict, start: str | None = None, recovery: str | None = None, dry_run: bool = False) -> int:
    start, recovery = start or cfg["daily"]["start_time"], recovery or cfg["daily"]["recovery_time"]
    pyexe = sys.executable
    if os.name == "nt":  # pythonw não abre janela de console
        pw = Path(pyexe).with_name("pythonw.exe")
        pyexe = str(pw) if pw.exists() else pyexe
    xml = task_xml(pyexe, cfg, start, recovery)
    xml_path = SKILL_DIR / "config" / f"{TASK_NAME}.xml"
    xml_path.write_text(xml, encoding="utf-16")
    print(f"XML da tarefa gravado em {xml_path}")
    if os.name != "nt" or dry_run:
        print("Não estou no Windows (ou --dry-run): para registrar, rode no PowerShell do Windows:\n"
              f'  schtasks /Create /TN "{TASK_NAME}" /XML "{xml_path}" /F')
        return 0
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"], capture_output=True, text=True)
    print(r.stdout or r.stderr)
    return r.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-daily")
    r.add_argument("--date")
    r.add_argument("--count", type=int)
    r.add_argument("--catalog", type=Path)
    r.add_argument("--voice", choices=["auto", "off", "required"], default="auto")
    r.add_argument("--offline", action="store_true")
    i = sub.add_parser("install-task")
    i.add_argument("--time")
    i.add_argument("--recovery")
    i.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    cfg = load_config()
    try:
        if a.cmd == "run-daily":
            res = run_daily(cfg, a.date, a.count, a.catalog, a.voice, offline=a.offline)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return res["exit_code"]
        if a.cmd == "install-task":
            return install_task(cfg, a.time, a.recovery, a.dry_run)
        st = load_state(cfg)
        day = dt.date.today().isoformat()
        print(json.dumps(st["days"].get(day, {}), ensure_ascii=False, indent=2))
        return 0
    except PipelineError as e:
        Logger("scheduler").error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
