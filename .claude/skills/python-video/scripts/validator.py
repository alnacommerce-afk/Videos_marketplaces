"""Quality gate: validação técnica (ffprobe/ffmpeg) + validação de conteúdo.

Um vídeo só pode virar READY se `validate()` devolver ok=True. Cada checagem tem severidade:
  error  -> reprova o vídeo
  warn   -> registrada, não reprova
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

from audio import loudnorm_params
from common import (Logger, PipelineError, ffprobe_json, load_config, load_json, run, save_json, which_tool)
from storyboard import expected_text


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "", severity: str = "error") -> bool:
        self.items.append({"name": name, "ok": bool(ok), "severity": severity, "detail": detail})
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.items if c["severity"] == "error")


def _fps(s: str) -> float:
    a, _, b = s.partition("/")
    return float(a) / float(b) if b and float(b) else float(a)


def moov_before_mdat(path: Path) -> bool:
    """Confere +faststart lendo as 'caixas' do topo do MP4."""
    with open(path, "rb") as f:
        pos, size_total = 0, path.stat().st_size
        seen_moov = False
        while pos < size_total:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            size, typ = struct.unpack(">I4s", hdr)
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            if typ == b"moov":
                seen_moov = True
            if typ == b"mdat":
                return seen_moov
            if size < 8:
                break
            pos += size
    return False


def sample_frames(path: Path, times: list[float], size=(135, 240)) -> list[np.ndarray]:
    ff, out = which_tool("ffmpeg"), []
    for t in times:
        r = run([ff, "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={size[0]}:{size[1]}",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=False)
        buf = r.stdout
        if len(buf) == size[0] * size[1] * 3:
            out.append(np.frombuffer(buf, dtype=np.uint8).reshape(size[1], size[0], 3))
        else:
            out.append(None)
    return out


def validate(mp4: Path, sb: dict, brief: dict, cfg: dict, render_report: dict | None, audio_report: dict | None,
             logger: Logger | None = None) -> dict:
    log = logger or Logger(echo=False)
    mp4 = Path(mp4)
    c = Checks()
    fmt, dur_cfg = sb["format"], cfg["duration"]

    # ------------------------------ técnica -------------------------------------
    if not c.add("arquivo existe", mp4.exists(), str(mp4)):
        return {"ok": False, "checks": c.items}
    size = mp4.stat().st_size
    c.add("tamanho do arquivo", 200_000 < size < 200_000_000, f"{size / 1e6:.2f} MB")
    try:
        probe = ffprobe_json(mp4)
    except PipelineError as e:
        c.add("arquivo abre (ffprobe)", False, str(e)[:200])
        return {"ok": False, "checks": c.items}
    c.add("arquivo abre (ffprobe)", True)
    vs = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    if not c.add("stream de vídeo presente", vs is not None):
        return {"ok": False, "checks": c.items}
    c.add("codec de vídeo H.264", vs["codec_name"] == "h264", vs["codec_name"])
    c.add("pix_fmt yuv420p", vs.get("pix_fmt") == "yuv420p", vs.get("pix_fmt", "?"))
    c.add("resolução", (vs["width"], vs["height"]) == (fmt["width"], fmt["height"]), f"{vs['width']}x{vs['height']}")
    fps = _fps(vs["r_frame_rate"])
    c.add("FPS", abs(fps - fmt["fps"]) < 0.01, f"{fps:.3f}")
    vdur = float(probe["format"]["duration"])
    c.add("duração dentro da meta", dur_cfg["min"] - 0.05 <= vdur <= dur_cfg["max"] + 0.05, f"{vdur:.2f}s (meta {dur_cfg['min']}–{dur_cfg['max']}s)")
    c.add("duração = storyboard", abs(vdur - sb["total_duration"]) < 0.12, f"{vdur:.2f}s vs {sb['total_duration']:.2f}s")
    if c.add("stream de áudio presente", au is not None):
        c.add("codec de áudio AAC", au["codec_name"] == "aac", au["codec_name"])
        adur = float(au.get("duration", vdur))
        c.add("áudio sincronizado (duração A≈V)", abs(adur - vdur) < 0.15, f"áudio {adur:.2f}s vs vídeo {vdur:.2f}s")
    c.add("faststart (moov antes de mdat)", moov_before_mdat(mp4))
    dec = run([which_tool("ffmpeg"), "-v", "error", "-i", str(mp4), "-f", "null", "-"], check=False)
    err = dec.stderr.decode("utf-8", "replace").strip()
    c.add("decodificação sem erros (sem corrupção)", dec.returncode == 0 and not err, err[:200])
    if au is not None:
        try:
            ln = loudnorm_params(mp4, cfg, pre=False)
            target = cfg["audio"]["loudnorm"]["I"]
            i_lufs, tp = float(ln["input_i"]), float(ln["input_tp"])
            c.add("áudio não está mudo", i_lufs > -40, f"{i_lufs:.1f} LUFS")
            c.add("loudness no alvo", abs(i_lufs - target) <= 2.5, f"{i_lufs:.1f} LUFS (alvo {target})")
            c.add("true peak seguro", tp <= -0.3, f"{tp:.1f} dBTP")
        except PipelineError as e:
            c.add("medição de loudness", False, str(e)[:200])

    # ------------------------------ conteúdo ------------------------------------
    c.add("produto correto (id)", sb["product_id"] == brief["product"]["id"], sb["product_id"])
    shas = {i["sha256"] for i in brief["product"]["images"]}
    c.add("imagens vêm do brief do produto", all(s["image_sha256"] in shas for s in sb["scenes"]))
    bad = []
    facts = {f["id"]: f for f in brief["confirmed_facts"]}
    for s in sb["scenes"]:
        tx = s.get("text")
        if not tx:
            continue
        exp = expected_text(tx["source"], brief, cfg)
        if exp is None or exp != tx["text"]:
            bad.append(f"cena {s['index']}: '{tx['text']}' ≠ fonte {tx['source']}")
        if tx["source"].startswith("fact:"):
            f = facts.get(tx["source"].split(":", 1)[1])
            if not f or not f["usable"] or f["risk"]:
                bad.append(f"cena {s['index']}: fato não utilizável")
        if tx.get("label") and expected_text(tx["label"], brief, cfg) is None:
            bad.append(f"cena {s['index']}: rótulo sem fonte")
        if s.get("voice") and s["voice"] != tx["text"]:
            bad.append(f"cena {s['index']}: fala diferente do texto rastreável")
    c.add("nenhuma característica inventada (todo texto rastreável a fato/nome/CTA)", not bad, "; ".join(bad)[:400])

    if render_report:
        sa = render_report["safe_area"]
        W, H = fmt["width"], fmt["height"]
        out_safe, small, low = [], [], []
        min_px = max(40, int(0.04 * W))
        for sc in render_report["scenes"]:
            for ly in sc["layers"]:
                x, y, w, h = ly["bbox"]
                if x < sa["left"] or y < sa["top"] or x + w > W - sa["right"] or y + h > H - sa["bottom"]:
                    out_safe.append(f"cena {ly['scene']} {ly['bbox']}")
                if ly["font_px"] < min_px:
                    small.append(f"cena {ly['scene']} {ly['font_px']}px")
                if ly["contrast"] < 3.0:
                    low.append(f"cena {ly['scene']} {ly['contrast']}")
        c.add("texto dentro da safe area", not out_safe, "; ".join(out_safe)[:300])
        c.add("texto legível (tamanho)", not small, "; ".join(small)[:300] + f" (mín. {min_px}px)")
        c.add("texto legível (contraste ≥ 3:1)", not low, "; ".join(low)[:300])
    else:
        c.add("relatório de render disponível", False, "sem render_report", severity="warn")

    last = sb["scenes"][-1]
    cta_ok = bool(last.get("text")) and last["text"]["role"] == "cta" and (last["duration"] - last["text"]["t_in"]) >= 1.2
    c.add("CTA presente e visível ≥ 1,2 s no final", cta_ok)
    first = sb["scenes"][0]
    c.add("gancho nos primeiros 2,5 s (cena 1 curta)", first["duration"] <= 3.2, f"{first['duration']:.2f}s", severity="warn")

    if audio_report:
        c.add("narração não cortada", not audio_report.get("voice_cut", False))
        if audio_report.get("has_voice") and "ducking_applied_db" in audio_report:
            c.add("ducking aplicado (trilha abaixa na fala)", audio_report["ducking_applied_db"] >= 6.0,
                  f"{audio_report['ducking_applied_db']} dB")
            gap = audio_report["voice_rms_db"] - audio_report["music_rms_db_during_voice"]
            c.add("música não cobre a voz (voz ≥ 12 dB acima)", gap >= 12.0, f"{gap:.1f} dB")
        c.add("trilha licenciada/sintetizada", audio_report["music"]["source"] in ("arquivo", "sintetizada"),
              json.dumps(audio_report["music"], ensure_ascii=False), severity="warn")

    # visual: amostras de quadros reais do MP4
    times = [0.1] + [s["start"] + s["duration"] * 0.6 for s in sb["scenes"]]
    frames = sample_frames(mp4, [min(t, vdur - 0.1) for t in times])
    ok_frames = [f for f in frames if f is not None]
    c.add("quadros amostrados", len(ok_frames) == len(frames), f"{len(ok_frames)}/{len(frames)}")
    if ok_frames:
        means = [float(f.mean()) for f in ok_frames]
        stds = [float(f.std()) for f in ok_frames]
        c.add("primeiro quadro não é preto (gancho imediato)", means[0] > 12, f"luma {means[0]:.0f}")
        c.add("nenhum quadro preto/estourado ou vazio", all(12 < m < 245 and s > 8 for m, s in zip(means, stds)),
              f"luma {min(means):.0f}–{max(means):.0f}, desvio ≥ {min(stds):.0f}")
        diffs = [float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) for a, b in zip(ok_frames, ok_frames[1:])]
        c.add("cenas visualmente distintas (sem vídeo congelado)", all(d > 3.0 for d in diffs),
              f"dif. mín. {min(diffs):.1f}" if diffs else "", severity="warn")

    result = {"ok": c.ok, "checks": c.items, "errors": [x["name"] for x in c.items if not x["ok"] and x["severity"] == "error"],
              "warnings": [x["name"] for x in c.items if not x["ok"] and x["severity"] == "warn"]}
    log.info("validação concluída", ok=result["ok"], erros=len(result["errors"]), avisos=len(result["warnings"]))
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Valida um vídeo gerado")
    ap.add_argument("job_dir", type=Path, help="pasta do job (contém video.mp4, storyboard.json, brief.json...)")
    a = ap.parse_args(argv)
    d = a.job_dir
    cfg = load_config()
    res = validate(d / "video.mp4", load_json(d / "storyboard.json"), load_json(d / "brief.json"), cfg,
                   load_json(d / "render_report.json", default={}) or None, load_json(d / "audio_report.json", default={}) or None)
    save_json(d / "validation.json", res)
    for ch in res["checks"]:
        print(("OK  " if ch["ok"] else ("AVISO" if ch["severity"] == "warn" else "FALHA")), ch["name"], "-", ch["detail"])
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
