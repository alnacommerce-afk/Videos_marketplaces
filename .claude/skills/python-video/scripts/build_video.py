"""Orquestra UM vídeo: brief → storyboard → locução → áudio → render → validação → entrega.

Uso manual:
  python build_video.py --catalog ../templates/catalog.example.json --product exemplo-001
  python build_video.py --url https://store.alna.sale/produto/xyz --archetype PREMIUM_CINEMATIC --voice off
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import shutil
import sys
import traceback
from pathlib import Path

import audio as A
import product_fetcher as pf
from common import (FAILED, PROCESSING, QUEUED, READY, RENDERING, VALIDATING, JobStatus, Logger, PipelineError, iso,
                    load_archetypes, load_config, output_dir, save_json, slugify, work_dir)
from renderer import Renderer
from storyboard import build_storyboard, choose_archetype, retime, storyboard_summary
from validator import validate


def script_text(sb: dict) -> str:
    lines = [f"# {sb['product_name']} — {sb['strategy']['archetype_label']} ({sb['total_duration']}s)", ""]
    for s in sb["scenes"]:
        tx = s["text"]["text"] if s["text"] else "(sem texto)"
        fonte = f" [{s['text']['source']}]" if s["text"] else ""
        lines.append(f"CENA {s['index']:02d} · {s['start']:.1f}–{s['start'] + s['duration']:.1f}s · {s['role']} · {s['purpose']}")
        lines.append(f"  texto: {tx}{fonte}")
        if s.get("voice") and s.get("voice_enabled"):
            lines.append(f"  fala : {s['voice']}")
        lines.append("")
    return "\n".join(lines)


def plan_voice(sb: dict, cfg: dict, job_dir: Path, mode: str, log: Logger, allow_voice_change: bool):
    """Gera os clipes de locução e re-temporiza o storyboard. Retorna ({cena: array}, info)."""
    if mode == "off":
        return {}, {"voice": "desativada"}
    try:
        A.voice_settings(cfg)
    except A.VoiceNotConfigured as e:
        if mode == "required":
            raise
        log.warn("sem narração: ElevenLabs não configurado (vídeo segue com texto + trilha)", motivo=str(e))
        return {}, {"voice": "não configurada"}
    from common import cache_dir
    clips, needs = {}, {}
    sr = cfg["audio"]["sample_rate"]
    for s in sb["scenes"]:
        if not s.get("voice"):
            continue
        mp3 = A.tts_elevenlabs(s["voice"], cfg, cache_dir(cfg), log, allow_voice_change)
        arr = A.decode_audio(mp3, sr)
        clips[s["index"]] = arr
        needs[s["index"]] = (0.12 if s["role"] == "HOOK" else 0.25) + len(arr) / sr + 0.2
    sb, dropped = retime(sb, needs, cfg)
    for d in dropped:
        clips.pop(d, None)
        log.warn("fala removida para caber em 15–18 s", cena=d)
    for s in sb["scenes"]:
        s["voice_enabled"] = s["index"] in clips
    return clips, {"voice": "ElevenLabs", "dropped": dropped}


def deliver(job_dir: Path, final_name: str, out_root: Path, day: str, log: Logger) -> Path:
    """Copia o MP4 e os arquivos de auditoria para a pasta final (cópia atômica: .partial → rename)."""
    dest_dir = out_root / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{final_name}.mp4"
    tmp = dest.with_suffix(".mp4.partial")
    shutil.copyfile(job_dir / "video.mp4", tmp)
    if tmp.stat().st_size != (job_dir / "video.mp4").stat().st_size:
        tmp.unlink(missing_ok=True)
        raise PipelineError("Cópia para a pasta final ficou com tamanho diferente.")
    os.replace(tmp, dest)
    audit = dest_dir / "_auditoria" / final_name
    audit.mkdir(parents=True, exist_ok=True)
    for f in ("brief.json", "storyboard.json", "script.md", "validation.json", "render_report.json", "audio_report.json",
              "job.json", "status.json", "video.contact.jpg"):
        if (job_dir / f).exists():
            shutil.copyfile(job_dir / f, audit / f)
    log.info("entregue", destino=str(dest))
    return dest


def build_video(brief: dict, cfg: dict, job_id: str, day: str | None = None, archetype: str | None = None,
                seed: int | None = None, voice_mode: str = "auto", music_avoid: list[str] | None = None,
                hook_avoid: list[str] | None = None, avoid_archetypes: list[str] | None = None,
                recent_archetypes: list[str] | None = None, out_root: Path | None = None, slot: int = 1,
                fmt_name: str | None = None, allow_voice_change: bool = False, deliver_output: bool = True) -> dict:
    """Retorna o resumo do job. Levanta PipelineError se falhar (job fica FAILED, nunca READY)."""
    day = day or dt.date.today().isoformat()
    job_dir = work_dir(cfg) / day / job_id
    if (job_dir / "status.json").exists():  # execução anterior interrompida (queda de energia etc.): recomeça limpo
        shutil.rmtree(job_dir, ignore_errors=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    log = Logger(job_id, extra_file=job_dir / "job.log.jsonl")
    st = JobStatus(job_dir, job_id, log, produto=brief["product"]["name"])
    summary = {"job_id": job_id, "product": brief["product"]["name"], "url": brief["product"]["url"], "queued_at": iso(),
               "status": st.status}
    try:
        st.set(PROCESSING)
        summary["started_at"] = iso()
        rng = random.Random(seed if seed is not None else 0)
        arch = archetype or choose_archetype(brief, rng, avoid_archetypes, recent_archetypes)
        sb = build_storyboard(brief, cfg, arch, seed, music_avoid, hook_avoid, fmt_name)
        summary["archetype"] = arch
        log.info("storyboard", arquetipo=arch, duracao=sb["total_duration"], musica=sb["strategy"]["music_profile"])
        for n in sb["notes"]:
            log.warn(n)
        save_json(job_dir / "brief.json", brief)

        clips, vinfo = plan_voice(sb, cfg, job_dir, voice_mode, log, allow_voice_change)
        sb["strategy"]["voice_requirement"] = "ElevenLabs" if clips else "sem narração"
        save_json(job_dir / "storyboard.json", sb)
        (job_dir / "script.md").write_text(script_text(sb), encoding="utf-8")
        summary["script"] = [{"cena": s["index"], "texto": s["text"]["text"] if s["text"] else None,
                              "fala": s["voice"] if s.get("voice_enabled") else None} for s in sb["scenes"]]
        print(storyboard_summary(sb), file=sys.stderr)

        wav = job_dir / "audio.wav"
        areport = A.build_mix(sb, cfg, clips, log, wav, seed=(seed or 0) + 11)
        save_json(job_dir / "audio_report.json", areport)
        ln = A.loudnorm_params(wav, cfg)

        st.set(RENDERING)
        summary["render_started_at"] = iso()
        rend = Renderer(sb, cfg, log)
        rreport = rend.render(job_dir / "video.mp4", wav, A.loudnorm_filter(ln, cfg))
        summary["render_finished_at"] = iso()
        save_json(job_dir / "render_report.json", rreport)

        st.set(VALIDATING)
        res = validate(job_dir / "video.mp4", sb, brief, cfg, rreport, areport, log)
        save_json(job_dir / "validation.json", res)
        if not res["ok"]:
            raise PipelineError("Reprovado no quality gate: " + "; ".join(res["errors"]))
        st.set(READY)
        summary.update({"status": READY, "duration": sb["total_duration"], "warnings": res["warnings"],
                        "validated": True, "local_path": str(job_dir / "video.mp4")})
        final = f"video_{slot:02d}_{slugify(brief['product']['name'], 30)}"
        summary["final_name"] = final
        if deliver_output:
            summary["final_path"] = str(deliver(job_dir, final, out_root or output_dir(cfg), day, log))
        summary["finished_at"] = iso()
        save_json(job_dir / "job.json", summary)
        return summary
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        st.fail(err[:500])
        summary.update({"status": FAILED, "error": err[:800], "finished_at": iso()})
        log.error("job falhou", erro=err[:300], trace=traceback.format_exc()[-1200:])
        save_json(job_dir / "job.json", summary)
        if isinstance(e, PipelineError):
            raise
        raise PipelineError(err) from e


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera um vídeo comercial a partir de um produto")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--catalog", type=Path, help="catálogo JSON manual (ver templates/catalog.example.json)")
    src.add_argument("--url", help="URL da página do produto na loja")
    ap.add_argument("--product", help="id ou nome do produto no catálogo (padrão: o primeiro)")
    ap.add_argument("--archetype", choices=sorted(load_archetypes()))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--voice", choices=["auto", "off", "required"], default="auto")
    ap.add_argument("--format", dest="fmt", choices=["9x16", "4x5", "1x1", "16x9"])
    ap.add_argument("--out", type=Path, help="pasta de saída (padrão: configurada / ALNA_OUTPUT_DIR)")
    ap.add_argument("--allow-voice-change", action="store_true")
    ap.add_argument("--no-deliver", action="store_true", help="não copia para a pasta final")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    cfg, log = load_config(), Logger("cli")
    try:
        if a.catalog:
            raws = pf.load_catalog(a.catalog)
            raw = next((r for r in raws if a.product in (r["id"], r["name"])), None) if a.product else raws[0]
            if raw is None:
                raise PipelineError(f"Produto '{a.product}' não está no catálogo.")
        else:
            http = pf.Http(cfg, log, offline=a.offline)
            raw = pf.extract_product_from_html(http.get(a.url), a.url)
        brief = pf.get_brief(raw, cfg, log, offline=a.offline)
        job_id = f"{slugify(brief['product']['name'], 24)}-{dt.datetime.now():%H%M%S}"
        res = build_video(brief, cfg, job_id, archetype=a.archetype, seed=a.seed, voice_mode=a.voice, out_root=a.out,
                          fmt_name=a.fmt, allow_voice_change=a.allow_voice_change, deliver_output=not a.no_deliver)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except PipelineError as e:
        log.error(str(e)[:400])
        return 1


if __name__ == "__main__":
    sys.exit(main())
