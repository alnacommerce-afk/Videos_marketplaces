"""Semana supervisionada: registre sua nota para cada vídeo e veja o que funciona.

  python feedback.py review                 # lista os vídeos de hoje (arquétipo, música, gancho, onde assistir)
  python feedback.py add video_01 4 "gostei do gancho, texto pequeno"      # nota 1–5 + comentário
  python feedback.py add video_02 2 "fundo estranho" --date 2026-10-06
  python feedback.py summary                # médias por arquétipo / música / gancho + comentários

As notas ficam em logs/feedback.jsonl. Elas servem para eu ajustar estilos e arquétipos (e, se você aprovar,
para o sorteio passar a favorecer o que você aprova).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

from common import iso, load_config, load_json, logs_dir, output_dir, work_dir


def _slots(cfg: dict, day: str) -> dict:
    st = work_dir(cfg) / "state.json"
    return (load_json(st, default={}) or {}).get("days", {}).get(day, {}).get("slots", {}) if st.exists() else {}


def cmd_review(cfg: dict, day: str) -> int:
    slots = _slots(cfg, day)
    if not slots:
        print(f"Nenhum vídeo registrado para {day}.")
        return 1
    out = output_dir(cfg) / day
    print(f"Vídeos de {day}  (pasta: {out})\n")
    for k in sorted(slots, key=int):
        s = slots[k]
        print(f"video_{int(k):02d}  {s.get('final_name', '')}")
        print(f"   arquétipo: {s.get('archetype')} | música: {s.get('music')} | gancho: {s.get('hook')}")
        print(f"   assista: {s.get('final_path') or '(ainda não entregue)'}")
        print(f"   folha de contato: {out / '_auditoria' / s.get('final_name', '') / 'video.contact.jpg'}")
    print("\nPara avaliar:  python feedback.py add video_01 4 \"comentário\"")
    print("Perguntas úteis: o gancho prendeu? o produto ficou bem visível? o texto está legível? a música combinou? você postaria?")
    return 0


def cmd_add(cfg: dict, video: str, score: int, note: str, day: str) -> int:
    if not 1 <= score <= 5:
        print("A nota deve ser de 1 a 5.")
        return 2
    num = "".join(ch for ch in video.replace("video_", "") if ch.isdigit())[:2]
    slot = str(int(num)) if num else None
    s = _slots(cfg, day).get(slot, {}) if slot else {}
    rec = {"ts": iso(), "day": day, "video": video, "score": score, "note": note,
           "archetype": s.get("archetype"), "music": s.get("music"), "hook": s.get("hook"), "product": s.get("product_id")}
    with open(logs_dir() / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Registrado: {video} ({day}) nota {score}" + (f" — {s.get('archetype')}" if s else " (vídeo não encontrado no estado; nota salva mesmo assim)"))
    return 0


def cmd_summary() -> int:
    p = logs_dir() / "feedback.jsonl"
    if not p.exists():
        print("Ainda não há avaliações.")
        return 1
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(rows)} avaliação(ões)\n")
    for field, title in (("archetype", "Arquétipo"), ("music", "Música"), ("hook", "Gancho")):
        agg = defaultdict(list)
        for r in rows:
            if r.get(field):
                agg[r[field]].append(r["score"])
        if agg:
            print(f"{title}:")
            for k, v in sorted(agg.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
                print(f"  {k:<22} média {sum(v) / len(v):.1f}  ({len(v)} vídeo(s))")
            print()
    print("Comentários:")
    for r in rows:
        if r.get("note"):
            print(f"  [{r['day']} {r['video']} nota {r['score']} · {r.get('archetype')}] {r['note']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review")
    r.add_argument("--date", default=dt.date.today().isoformat())
    a_ = sub.add_parser("add")
    a_.add_argument("video")
    a_.add_argument("score", type=int)
    a_.add_argument("note", nargs="?", default="")
    a_.add_argument("--date", default=dt.date.today().isoformat())
    sub.add_parser("summary")
    a = ap.parse_args(argv)
    cfg = load_config()
    if a.cmd == "review":
        return cmd_review(cfg, a.date)
    if a.cmd == "add":
        return cmd_add(cfg, a.video, a.score, a.note, a.date)
    return cmd_summary()


if __name__ == "__main__":
    sys.exit(main())
