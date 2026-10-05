"""Analisa vídeos de REFERÊNCIA (arquivos .mp4 que você já tem no PC) para o Claude estudar a estrutura:
ritmo de cortes, duração da 1ª cena (gancho), tamanho médio de plano, loudness/silêncio e uma prancha de quadros nos
momentos-chave (0,3 s · 1 s · 2 s · 3 s · cada corte · final). Não baixa nada da internet e não copia conteúdo:
só mede e gera uma prancha para estudo.

  python analisar_referencia.py C:\\ALNA\\referencias\\video1.mp4 [video2.mp4 ...]
  python analisar_referencia.py C:\\ALNA\\referencias            # pasta inteira

Saída (em referencias_analise\\<nome>\\): analise.json + prancha.jpg. Mande a prancha e o analise.json ao Claude.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from common import SKILL_DIR, ffprobe_json, run, save_json, which_tool


def detect_cuts(path: str, thr: float = 0.30) -> list[float]:
    r = run([which_tool("ffmpeg"), "-v", "info", "-i", path, "-vf", f"select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"], check=False)
    txt = r.stderr.decode("utf-8", "replace")
    return [round(float(m), 3) for m in re.findall(r"pts_time:([0-9.]+)", txt)]


def loudness(path: str) -> dict:
    r = run([which_tool("ffmpeg"), "-v", "info", "-i", path, "-vn", "-af", "ebur128=peak=true,silencedetect=n=-45dB:d=0.4", "-f", "null", "-"], check=False)
    txt = r.stderr.decode("utf-8", "replace")
    out = {}
    m = re.search(r"I:\s+(-?[0-9.]+) LUFS", txt[txt.rfind("Summary"):] if "Summary" in txt else txt)
    if m:
        out["lufs"] = float(m.group(1))
    m = re.search(r"LRA:\s+([0-9.]+) LU", txt)
    if m:
        out["lra"] = float(m.group(1))
    out["silent_stretches"] = len(re.findall(r"silence_start", txt))
    return out


def frame_at(path: str, t: float, size: tuple[int, int]) -> Image.Image | None:
    r = run([which_tool("ffmpeg"), "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=False)
    n = size[0] * size[1] * 3
    return Image.frombytes("RGB", size, r.stdout[:n]) if len(r.stdout) >= n else None


def analyze(path: Path, out_dir: Path) -> dict:
    info = ffprobe_json(str(path))
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    dur = float(info["format"]["duration"])
    cuts = [c for c in detect_cuts(str(path)) if 0.15 < c < dur - 0.1]
    bounds = [0.0] + cuts + [dur]
    shots = [round(b - a, 2) for a, b in zip(bounds, bounds[1:])]
    res = {"arquivo": path.name, "duracao_s": round(dur, 2), "resolucao": f"{v['width']}x{v['height']}", "fps": v.get("r_frame_rate"),
           "cortes": len(cuts), "cortes_por_10s": round(len(cuts) / dur * 10, 1), "primeiro_corte_s": cuts[0] if cuts else None,
           "plano_medio_s": round(statistics.mean(shots), 2), "plano_mediano_s": round(statistics.median(shots), 2),
           "plano_mais_curto_s": min(shots), "plano_mais_longo_s": max(shots), "tempos_dos_cortes": cuts[:60],
           "audio": loudness(str(path)) if any(s["codec_type"] == "audio" for s in info["streams"]) else {"sem_audio": True}}
    marks = sorted({0.3, 1.0, 2.0, 3.0, *[c + 0.15 for c in cuts[:14]], max(dur - 0.5, 0)})
    marks = [m for m in marks if m < dur][:18]
    tw, th = 270, 480
    cols = 6
    rows = (len(marks) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(marks):
        fr = frame_at(str(path), t, (tw, th))
        if fr:
            sheet.paste(fr, ((i % cols) * tw, (i // cols) * th))
            d.rectangle(((i % cols) * tw, (i // cols) * th, (i % cols) * tw + 92, (i // cols) * th + 26), fill=(0, 0, 0))
            d.text(((i % cols) * tw + 6, (i // cols) * th + 6), f"{t:.1f}s", fill=(255, 255, 0))
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(out_dir / "prancha.jpg", quality=88)
    save_json(out_dir / "analise.json", res)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Analisa vídeos de referência (ritmo, gancho, som) para estudo")
    ap.add_argument("alvos", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("referencias_analise"))
    a = ap.parse_args(argv)
    files = []
    for t in a.alvos:
        files += sorted(t.glob("*.mp4")) if t.is_dir() else [t]
    if not files:
        print("Nenhum .mp4 encontrado.")
        return 1
    for f in files:
        res = analyze(f, a.out / f.stem)
        print(f"{f.name}: {res['duracao_s']}s · {res['cortes']} cortes ({res['cortes_por_10s']}/10s) · plano médio {res['plano_medio_s']}s · "
              f"1º corte em {res['primeiro_corte_s']}s · áudio {res['audio']}")
    print(f"Pronto: veja {a.out}\\<nome>\\prancha.jpg e analise.json e mande ao Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
