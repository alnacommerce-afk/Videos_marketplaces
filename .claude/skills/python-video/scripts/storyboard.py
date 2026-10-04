"""Storyboard: do Product Brief a uma lista de cenas executáveis.

Regra de veracidade aplicada aqui: todo texto na tela / fala tem uma `source` que o validador
consegue recalcular a partir do brief:
    fact:<id>        -> literalmente o texto do fato confirmado
    name             -> nome do produto
    template:question-> "Já conhece {nome}?" (pergunta neutra, sem alegar nada)
    cta:<i>          -> uma das chamadas fixas da marca
    label:<kind>     -> rótulo neutro do tipo de fato (Medidas, Material...)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image

from camera import focal_candidates, plan_camera
from common import (PipelineError, format_spec, iso, load_archetypes, load_config, load_json, save_json)

KIND_LABEL = {"dimension": "Medidas", "material": "Material", "quantity": "Quantidade", "color": "Cor",
              "use": "Uso", "gift": "Presente", "contents": "Na embalagem", "variation": "Variações"}

SFX_FOR_TRANSITION = {"whip": "whoosh", "motion": "swipe", "zoom": "whoosh", "directional_wipe": "swipe",
                      "light_sweep": "swipe", "speed_ramp": "whoosh"}

HOOK_STYLES = ["fact_hook", "name_reveal", "question", "silent_macro"]


# ----------------------------------------------------------------------------
# Elegibilidade e escolha de arquétipo
# ----------------------------------------------------------------------------
def usable_facts(brief: dict) -> list[dict]:
    return [f for f in brief["confirmed_facts"] if f["usable"] and f["kind"] != "price"]


def displayable(brief: dict) -> list[dict]:
    return [f for f in usable_facts(brief) if f["display"]]


def eligibility(brief: dict, name: str, spec: dict) -> tuple[bool, str]:
    req = spec.get("requires", {})
    n_img, facts = len(brief["product"]["images"]), usable_facts(brief)
    if n_img < req.get("min_images", 1):
        return False, f"precisa de {req['min_images']} imagens"
    if len(displayable(brief)) < req.get("min_facts", 0):
        return False, f"precisa de {req['min_facts']} fatos confirmados exibíveis"
    kinds = req.get("fact_kinds_any")
    if kinds and not any(f["kind"] in kinds for f in facts):
        return False, f"precisa de fato do tipo {kinds}"
    return True, ""


def eligible_archetypes(brief: dict, archetypes: dict | None = None) -> dict[str, str]:
    """{nome: motivo} — motivo vazio = elegível."""
    archetypes = archetypes or load_archetypes()
    return {n: eligibility(brief, n, s)[1] for n, s in archetypes.items()}


def choose_archetype(brief: dict, rng: random.Random, avoid_archetypes: list[str] | None = None,
                     recent: list[str] | None = None, archetypes: dict | None = None) -> str:
    """Escolhe entre os elegíveis, penalizando os usados recentemente (variedade)."""
    archetypes = archetypes or load_archetypes()
    avoid, recent = set(avoid_archetypes or []), list(recent or [])
    ok = [n for n, why in eligible_archetypes(brief, archetypes).items() if not why]
    if not ok:
        raise PipelineError("Nenhum arquétipo elegível para este produto com os fatos confirmados.")
    pool = [n for n in ok if n not in avoid] or ok

    def weight(n):
        w = 1.0
        if n in recent:
            w *= 0.25 ** (1 + (len(recent) - 1 - recent.index(n)) * 0.0)
        # PROBLEM/GIFT/BEFORE só existem com fatos manuais: se elegíveis, merecem prioridade (são mais específicos)
        if archetypes[n].get("requires", {}).get("fact_kinds_any"):
            w *= 1.6
        return w
    return rng.choices(pool, weights=[weight(n) for n in pool], k=1)[0]


# ----------------------------------------------------------------------------
# Texto rastreável
# ----------------------------------------------------------------------------
def expected_text(source: str, brief: dict, cfg: dict) -> str | None:
    """Recalcula o texto que uma `source` deve produzir. Usado aqui e no validador."""
    kind, _, arg = source.partition(":")
    if kind == "fact":
        for f in brief["confirmed_facts"]:
            if f["id"] == arg and f["usable"]:
                return f["display"] or f["text"]
        return None
    if kind == "name":
        return brief["product"]["name"]
    if kind == "template" and arg == "question":
        return cfg["brand"]["question_template"].format(name=brief["product"]["name"])
    if kind == "cta":
        opts = list(cfg["brand"]["cta_options"]) + list(cfg["brand"].get("cta_by_pace", {}).values())
        return opts[int(arg)] if arg.isdigit() and int(arg) < len(opts) else None
    if kind == "label":
        return KIND_LABEL.get(arg)
    return None


def _cta_options(cfg: dict) -> list[str]:
    return list(cfg["brand"]["cta_options"]) + list(cfg["brand"].get("cta_by_pace", {}).values())


class FactPool:
    def __init__(self, brief: dict, rng: random.Random):
        self.items = displayable(brief)
        rng.shuffle(self.items)
        self.used: set[str] = set()

    def take(self, kinds: list[str] | None = None, prefer: list[str] | None = None, max_len: int = 64):
        cands = [f for f in self.items if f["id"] not in self.used and len(f["display"]) <= max_len]
        if kinds:
            cands = [f for f in cands if f["kind"] in kinds]
        if not cands:
            return None
        if prefer:
            cands.sort(key=lambda f: prefer.index(f["kind"]) if f["kind"] in prefer else 99)
        f = cands[0]
        self.used.add(f["id"])
        return f



# ----------------------------------------------------------------------------
# Continuidade de movimento (movement match)
# ----------------------------------------------------------------------------
_AXIS = {"pan_h": "x", "diagonal": "x", "pan_v": "y", "push_in": "z", "pull_out": "z"}


def momentum_of(cam: dict):
    """Eixo e sentido em que a câmera 'termina' a cena: ('x'|'y'|'z', ±1) ou None."""
    m = cam["move"]
    if m in ("pan_h", "diagonal", "pan_v"):
        return (_AXIS[m], cam.get("dir", 1))
    if m == "push_in":
        return ("z", 1)
    if m == "pull_out":
        return ("z", -1)
    return None


def choose_move(options: list[str], mom, rng: random.Random) -> str:
    """Entre os movimentos permitidos pela cena, prefere o que continua o impulso da cena anterior
    (mesmo eixo/sentido); evita inverter bruscamente (ex.: push-in seguido de pull-out)."""
    if len(options) == 1 or mom is None:
        return rng.choice(options)

    def score(o):
        axis = _AXIS.get(o)
        if axis == mom[0]:
            if axis == "z":
                return 2.0 if (o == "push_in") == (mom[1] > 0) else 0.3
            return 2.0
        return 1.0
    return rng.choices(options, weights=[score(o) for o in options], k=1)[0]


def continuity_stats(scenes: list[dict]) -> dict:
    """Quantas trocas mantêm o sentido do movimento. Inversões de pan (esquerda↔direita) são o que 'quebra' o olhar."""
    pairs = rev = zrev = 0
    prev = None
    for s in scenes:
        cur = momentum_of(s["camera"])
        if prev and cur:
            if prev[0] == cur[0] and cur[0] in ("x", "y"):
                pairs += 1
                rev += int(prev[1] != cur[1])
            elif prev[0] == cur[0] == "z":
                pairs += 1
                zrev += int(prev[1] != cur[1])
        prev = cur or prev
    return {"pairs": pairs, "pan_reversals": rev, "zoom_reversals": zrev}


# ----------------------------------------------------------------------------
# Escolha de foto por papel (texto alternativo publicado na loja)
# ----------------------------------------------------------------------------
ARCH_IMAGE_PREF = {"LIFESTYLE": "lifestyle", "PRODUCT_DEMONSTRATION": "lifestyle", "HOW_TO_USE": "lifestyle",
                   "UNBOXING": "packaging", "GIFT_ANGLE": "packaging"}


def pick_image(shot: str, archetype: str, imgs: list[dict], last_img: int, used: set, rng: random.Random) -> int:
    """Planos 'hero' usam a capa (produto claro e dominante). Planos de detalhe/macro preferem fotos cujo texto
    alternativo diz 'close/detalhe/textura'; o segundo detalhe segue a preferência do arquétipo (ex.: foto de uso
    para LIFESTYLE). Evita repetir a foto anterior e prefere as ainda não usadas. Só decide ENQUADRAMENTO."""
    if shot.startswith("hero") or len(imgs) == 1:
        return 0
    want = ARCH_IMAGE_PREF.get(archetype) if shot == "detail2" else "detail"
    cands = [i for i in range(len(imgs)) if i != last_img] or list(range(len(imgs)))
    preferred = [i for i in cands if want and imgs[i].get("role") == want] or cands
    fresh = [i for i in preferred if i not in used] or preferred
    return rng.choice(fresh)


# ----------------------------------------------------------------------------
# Construção
# ----------------------------------------------------------------------------
def _frames(seconds: float, fps: int) -> int:
    return max(1, round(seconds * fps))


def _split_durations(weights: list[float], total_s: float, fps: int) -> list[float]:
    total_f = _frames(total_s, fps)
    raw = [w / sum(weights) * total_f for w in weights]
    fr = [max(int(fps * 1.2), round(r)) for r in raw]  # nenhuma cena < 1,2 s
    diff = total_f - sum(fr)
    i = 0
    while diff != 0:
        j = i % len(fr)
        step = 1 if diff > 0 else -1
        if fr[j] + step >= int(fps * 1.2):
            fr[j] += step
            diff -= step
        i += 1
        if i > 10000:
            break
    return [f / fps for f in fr]


def build_storyboard(brief: dict, cfg: dict, archetype: str, seed: int | None = None,
                     music_avoid: list[str] | None = None, hook_avoid: list[str] | None = None,
                     fmt_name: str | None = None) -> dict:
    archetypes = load_archetypes()
    if archetype not in archetypes:
        raise PipelineError(f"Arquétipo desconhecido: {archetype}")
    spec = archetypes[archetype]
    ok, why = eligibility(brief, archetype, spec)
    if not ok:
        raise PipelineError(f"Arquétipo {archetype} não é elegível: {why}")
    rng = random.Random(seed if seed is not None else hash(brief["product"]["id"]) & 0xFFFF)
    fmt = format_spec(cfg, fmt_name)
    W, H, fps = fmt["width"], fmt["height"], fmt["fps"]
    dcfg = cfg["duration"]
    pace_total = {"fast": dcfg["min"] + 0.5, "medium": dcfg["target"], "slow": dcfg["max"] - 0.5}[spec["pace"]]
    total = round(min(max(pace_total + rng.uniform(-0.3, 0.3), dcfg["min"] + 0.2), dcfg["max"] - 0.2), 2)
    # b-roll: só entra se há clipe baixado cujo tema é justificado por um fato de USO confirmado e exibível
    use_ok = {f["id"] for f in brief["confirmed_facts"] if f["usable"] and f["kind"] == "use" and f["display"]}
    broll_items = [b for b in (brief.get("broll") or []) if b["fact_id"] in use_ok][: cfg.get("broll", {}).get("max_per_video", 1)]
    beats, n_amb = [], 0
    for b in spec["beats"]:
        if b.get("optional") == "broll":
            if n_amb >= len(broll_items):
                continue
            n_amb += 1
        beats.append(b)
    durs = _split_durations([b["w"] for b in beats], total, fps)

    # imagens + pontos de interesse
    imgs = brief["product"]["images"]
    focals = []
    sizes = []
    for im in imgs:
        with Image.open(im["path"]) as pil:
            pil = pil.convert("RGB")
            sizes.append(pil.size)
            focals.append(focal_candidates(pil, 4))
    pool = FactPool(brief, rng)
    for it in broll_items[:n_amb]:
        pool.used.add(it["fact_id"])  # o fato de uso fica reservado para a cena do clipe (não repete em outra cena)
    clip_i = 0
    pace_cta = cfg["brand"].get("cta_by_pace", {}).get(spec["pace"])
    cta_idx = _cta_options(cfg).index(pace_cta) if pace_cta in _cta_options(cfg) else 0

    # estilo de gancho (variedade entre vídeos)
    hook_pool = [h for h in HOOK_STYLES if h not in set(hook_avoid or [])] or HOOK_STYLES
    if not pool.items:
        hook_pool = [h for h in hook_pool if h != "fact_hook"] or ["name_reveal"]
    hook_style = rng.choice(hook_pool)

    scenes, t, last_img, detail_i = [], 0.0, -1, 0
    mom = None  # impulso de câmera da cena anterior
    used_imgs: set = set()
    notes: list[str] = []
    for i, (beat, dur) in enumerate(zip(beats, durs)):
        shot = beat["shot"]
        if beat.get("optional") == "broll":
            it = broll_items[clip_i]
            clip_i += 1
            fct = next(f for f in brief["confirmed_facts"] if f["id"] == it["fact_id"])
            tr, tw = beat.get("transition", "dissolve"), beat.get("tw", 0.4)
            txt = {"source": f"fact:{fct['id']}", "role": "fact", "text": fct["display"], "anim": beat.get("anim", "words"),
                   "t_in": 0.3, "position": "bottom"}
            if expected_text(txt["source"], brief, cfg) != txt["text"]:
                raise PipelineError(f"Texto da cena {i + 1} não bate com a fonte {txt['source']}")
            keep = ("theme", "fact_id", "path", "provider", "id", "page_url", "user", "tags", "duration", "width", "height", "rendition", "sha256")
            scenes.append({
                "index": i + 1, "role": beat["role"], "start": round(t, 3), "duration": round(dur, 3),
                "image_index": None, "image": None, "image_sha256": None,
                "camera": {"shot": "broll", "move": "static", "dir": 1, "fill": 1.0, "z0": 1.0, "z1": 1.0, "c0": [0.5, 0.5],
                           "c1": [0.5, 0.5], "ease": "in_out", "parallax": False},
                "focus_pull": False, "clip": {k: it[k] for k in keep if k in it}, "illustrative": True,
                "transition_in": {"type": tr, "duration": tw, "direction": mom[1] if (mom and mom[0] == "x") else 1},
                "text": txt, "voice": txt["text"], "sfx": [],
                "purpose": f"AMBIENTE · clipe ilustrativo do tema '{it['theme']}' (fato de uso {fct['id']})",
            })
            t += dur
            continue
        # imagem: planos "hero*" usam a capa; detalhes giram pelas demais (variedade de fotos)
        img_i = pick_image(shot, archetype, imgs, last_img, used_imgs, rng)
        used_imgs.add(img_i)
        move = choose_move(beat["move"], mom, rng)
        pan_dir = mom[1] if (mom and mom[0] == _AXIS.get(move) and move in ("pan_h", "diagonal", "pan_v")) else None
        transition = beat.get("transition", "hard_cut")
        start_from = None
        if transition == "match_cut" and scenes and scenes[-1]["image_index"] == img_i:
            start_from = scenes[-1]["camera"]
        cam = plan_camera(shot, move, sizes[img_i], focals[img_i], W, H, rng, start_from, direction=pan_dir)
        tw = beat.get("tw", 0.0) if transition not in ("hard_cut", "match_cut") else 0.0

        text, voice = None, None
        slot = beat.get("text", "none")
        kind, _, arg = slot.partition(":")
        kinds = arg.split(",") if arg else None
        if slot == "none":
            pass
        elif kind == "hook":
            if beat["role"] == "HOOK":
                style = hook_style
            else:
                style = "name_reveal"
            if style == "silent_macro":
                style = "name_reveal" if beat["role"] != "HOOK" else None
            if style == "fact_hook":
                f = pool.take(prefer=["use", "characteristic", "material", "quantity", "color", "dimension"], max_len=44)
                text = {"source": f"fact:{f['id']}", "role": "headline", "text": f["display"]} if f else None
            if style == "question" and len(brief["product"]["name"]) <= 38:
                text = {"source": "template:question", "role": "headline",
                        "text": expected_text("template:question", brief, cfg)}
            if text is None and style:
                text = {"source": "name", "role": "headline", "text": brief["product"]["name"]}
        elif kind == "name":
            text = {"source": "name", "role": "name", "text": brief["product"]["name"]}
        elif kind in ("fact", "fact_card"):
            prefer = ["dimension", "material", "quantity", "use", "color"]
            f = pool.take(kinds=kinds, prefer=prefer, max_len=64 if kind == "fact_card" else 44) if kinds else \
                pool.take(prefer=prefer, max_len=64 if kind == "fact_card" else 44)
            if f is None and kinds:  # tipo pedido não existe: não inventa, tenta qualquer fato real
                f = pool.take(prefer=prefer)
            if f:
                text = {"source": f"fact:{f['id']}", "role": "card" if kind == "fact_card" else "fact", "text": f["display"],
                        "label": expected_text(f"label:{f['kind']}", brief, cfg) and f"label:{f['kind']}"}
            else:
                notes.append(f"cena {i + 1} ({beat['role']}): sem fato confirmado disponível, ficou sem texto")
        elif kind == "cta":
            text = {"source": f"cta:{cta_idx}", "role": "cta", "text": _cta_options(cfg)[cta_idx]}
        if text:
            exp = expected_text(text["source"], brief, cfg)
            if exp != text["text"]:
                raise PipelineError(f"Texto da cena {i + 1} não bate com a fonte {text['source']}")
            text["anim"] = beat.get("anim", "fade")
            text["t_in"] = 0.25 if beat["role"] != "HOOK" else 0.12
            text["position"] = {"headline": "top", "name": "bottom", "fact": "bottom", "card": "bottom", "cta": "bottom"}[text["role"]]
            if text["role"] == "cta":
                text["t_in"] = 0.35
            voice = text["text"]

        sfx = []
        if beat.get("sfx"):
            sfx.append({"type": beat["sfx"], "at": round(text["t_in"], 2) if (text and beat["sfx"] in ("click", "soft_impact", "pop")) else 0.0})
        if transition in SFX_FOR_TRANSITION and tw:
            sfx.append({"type": SFX_FOR_TRANSITION[transition], "at": round(-tw * 0.8, 2)})

        scenes.append({
            "index": i + 1, "role": beat["role"], "start": round(t, 3), "duration": round(dur, 3),
            "image_index": img_i, "image": imgs[img_i]["path"], "image_sha256": imgs[img_i]["sha256"],
            "camera": cam, "focus_pull": bool(beat.get("focus_pull")),
            "transition_in": {"type": transition, "duration": tw,
                              "direction": mom[1] if (mom and mom[0] == "x") else 1}, "text": text,
            "voice": voice, "sfx": sfx,
            "purpose": f"{beat['role']} · plano {shot} · movimento {move}",
        })
        t += dur
        last_img = img_i
        mom = momentum_of(cam) or mom

    music = [m for m in spec["music"] if m not in set(music_avoid or [])] or spec["music"]
    profile = rng.choice(music)
    # a fala é decidida depois (precisa de ElevenLabs); aqui só o roteiro candidato
    script = [{"scene": s["index"], "text": s["voice"]} for s in scenes if s["voice"]]
    sb = {
        "schema": 1, "created_at": iso(),
        "product_id": brief["product"]["id"], "product_name": brief["product"]["name"],
        "product_url": brief["product"]["url"],
        "format": fmt, "total_duration": round(t, 3),
        "strategy": {"archetype": archetype, "archetype_label": spec["label"], "pace": spec["pace"],
                     "hook_style": hook_style, "music_profile": profile, "style": spec["style"],
                     "seed": seed, "voice_requirement": "optional", "broll_clips": n_amb},
        "scenes": scenes, "voice_script": script, "notes": notes, "continuity": continuity_stats(scenes),
    }
    brief["video_strategy"] = sb["strategy"]
    return sb


def storyboard_summary(sb: dict) -> str:
    lines = [f"{sb['product_name']} · {sb['strategy']['archetype']} · {sb['total_duration']}s · música {sb['strategy']['music_profile']}"]
    for s in sb["scenes"]:
        tx = f"“{s['text']['text']}”" if s["text"] else "—"
        lines.append(f"  CENA {s['index']:02d} {s['start']:5.1f}–{s['start'] + s['duration']:4.1f}s  {s['role']:<15} "
                     f"{s['camera']['shot']:<9} {s['camera']['move']:<9} {s['transition_in']['type']:<16} {tx}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera o storyboard a partir de um brief.json")
    ap.add_argument("brief", type=Path)
    ap.add_argument("--archetype")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    cfg, brief = load_config(), load_json(a.brief)
    rng = random.Random(a.seed)
    arch = a.archetype or choose_archetype(brief, rng)
    sb = build_storyboard(brief, cfg, arch, a.seed)
    print(storyboard_summary(sb))
    if a.out:
        save_json(a.out, sb)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ----------------------------------------------------------------------------
# Re-temporização para caber a locução (sem cortar fala)
# ----------------------------------------------------------------------------
def retime(sb: dict, needs: dict[int, float], cfg: dict) -> tuple[dict, list[int]]:
    """Garante que cada cena com fala dure o suficiente e que o total fique entre min e max.
    needs: {indice_da_cena: segundos mínimos}. Se não couber, remove a fala das cenas menos
    importantes (nunca HOOK/CTA primeiro) e tenta de novo. Retorna (storyboard, cenas_sem_fala)."""
    fps = sb["format"]["fps"]
    dmin, dmax = cfg["duration"]["min"], cfg["duration"]["max"]
    dropped: list[int] = []
    needs = dict(needs)
    for _ in range(len(needs) + 1):
        base = [s["duration"] for s in sb["scenes"]]
        want = [max(d, needs.get(s["index"], 0.0), 1.2) for d, s in zip(base, sb["scenes"])]
        total = sum(want)
        if total > dmax:
            # comprime as cenas que não têm exigência de fala, até 1.2 s
            slack = [(w - max(needs.get(s["index"], 0.0), 1.2)) for w, s in zip(want, sb["scenes"])]
            over = total - dmax + 0.02
            if sum(slack) >= over:
                scale = over / sum(slack)
                want = [w - sl * scale for w, sl in zip(want, slack)]
                total = sum(want)
        if total <= dmax + 1e-6:
            if total < dmin:
                k = (dmin + 0.2) / total
                want = [w * k for w in want]
            # arredonda para quadros inteiros e fecha a soma
            fr = [max(1, round(w * fps)) for w in want]
            target = round(min(max(sum(fr) / fps, dmin + 0.05), dmax - 0.05) * fps)
            i = 0
            while sum(fr) != target:
                j = i % len(fr)
                fr[j] += 1 if sum(fr) < target else -1
                i += 1
            t = 0.0
            for s, f in zip(sb["scenes"], fr):
                s["duration"], s["start"] = round(f / fps, 3), round(t, 3)
                t += f / fps
            sb["total_duration"] = round(t, 3)
            return sb, dropped
        # não coube: derruba a fala da cena não-HOOK/CTA com maior exigência
        cands = [s for s in sb["scenes"] if s["index"] in needs and s["role"] not in ("HOOK", "CTA")] or \
                [s for s in sb["scenes"] if s["index"] in needs]
        if not cands:
            break
        worst = max(cands, key=lambda s: needs[s["index"]])
        dropped.append(worst["index"])
        needs.pop(worst["index"])
    raise PipelineError("Não foi possível encaixar a locução em 15–18 s mesmo cortando falas.")


# ----------------------------------------------------------------------------
# Corte na batida (beat-lock)
# ----------------------------------------------------------------------------
def beat_lock(sb: dict, cfg: dict, music_plan: dict, needs: dict[int, float] | None = None, tol: float = 0.10):
    """Ajusta as durações para que TODA troca de cena (e o fim do vídeo) caia numa batida da trilha.

    Trilha sintetizada: o andamento pode variar ±`tol` (10%) para achar a grade que menos desloca os cortes;
    trilha de arquivo: só trava se o nome tiver o BPM (ex.: `premium_92bpm.mp3`), com a faixa começando no tempo 1.
    Respeita: cena ≥ 1,2 s, tempo mínimo da narração (`needs`) e duração total 15–18 s.
    Retorna (storyboard, info|None); None = não foi possível travar (o vídeo segue com cortes livres)."""
    import math
    base = music_plan.get("bpm")
    if not base:
        return sb, None
    fps = sb["format"]["fps"]
    dmin, dmax = cfg["duration"]["min"], cfg["duration"]["max"]
    needs = needs or {}
    scenes = sb["scenes"]
    ends, acc = [], 0.0
    for s in scenes:
        acc += s["duration"]
        ends.append(acc)
    cands = [base * (1 + d / 200.0) for d in range(-int(tol * 200), int(tol * 200) + 1)] if music_plan.get("tunable") else [base]
    best = None
    for bpm in cands:
        p = 60.0 / bpm
        prev, plan = 0.0, []
        for i, s in enumerate(scenes):
            mind = max(1.2, needs.get(s["index"], 0.0))
            k = max(round(ends[i] / p), math.ceil((prev + mind) / p - 1e-9))
            bf = round(k * p * fps) / fps
            while bf - prev < mind - 1e-9:
                k += 1
                bf = round(k * p * fps) / fps
            plan.append((k, bf))
            prev = bf
        total = plan[-1][1]
        if not (dmin + 0.05 <= total <= dmax - 0.05):
            continue
        cost = sum(abs(bf - ends[i]) for i, (k, bf) in enumerate(plan)) \
            + 0.05 * sum(1 for k, _ in plan if k % 4) + 0.5 * abs(bpm - base) / base
        if best is None or cost < best[0]:
            best = (cost, bpm, plan)
    if best is None:
        return sb, None
    _, bpm, plan = best
    p = 60.0 / bpm
    t = 0.0
    for s, (k, bf) in zip(scenes, plan):
        s["start"], s["duration"] = round(t, 3), round(bf - t, 3)
        t = bf
    sb["total_duration"] = round(t, 3)
    err = max(abs(bf - k * p) for k, bf in plan)
    info = {**{k_: v for k_, v in music_plan.items() if k_ != "tunable"}, "bpm": round(bpm, 2), "locked": True,
            "max_error_ms": round(err * 1000, 1), "cut_beats": [k for k, _ in plan],
            "on_downbeat": sum(1 for k, _ in plan if k % 4 == 0)}
    sb["music"] = info
    return sb, info
