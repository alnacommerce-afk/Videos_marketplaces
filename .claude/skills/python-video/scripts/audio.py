"""Áudio: locução (ElevenLabs), trilha (pasta licenciada ou síntese própria), efeitos, ducking e mix.

* Locução: voz ÚNICA da marca via ELEVENLABS_VOICE_ID (travada em config/voice.lock.json).
* Trilha: usa arquivos que VOCÊ colocar em music/ (você responde pela licença). Sem arquivos,
  sintetiza uma trilha original por perfil (PREMIUM, LIFESTYLE, ENERGETIC, MODERN, ARTISANAL, MINIMAL),
  portanto sem risco de copyright.
* Efeitos: sintetizados (whoosh, impact, click, pop, swipe, rise, hit...).
* Ducking: a trilha abaixa sozinha enquanto há voz.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import wave
from pathlib import Path

import numpy as np

from common import (Logger, PipelineError, cache_dir, iso, load_json, music_dir, run, save_json, which_tool,
                    CONFIG_PATH)

SR_DEFAULT = 48000
PROFILES = {
    "PREMIUM":   {"bpm": 76,  "chords": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]], "pad": 1.0, "pluck": "sparse", "drums": "heart", "bass": 0.6},
    "LIFESTYLE": {"bpm": 100, "chords": [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]], "pad": 0.5, "pluck": "arp8", "drums": "shaker", "bass": 0.7},
    "ENERGETIC": {"bpm": 126, "chords": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]], "pad": 0.4, "pluck": "arp16", "drums": "four", "bass": 1.0},
    "MODERN":    {"bpm": 108, "chords": [[50, 53, 57], [46, 50, 53], [53, 57, 60], [48, 52, 55]], "pad": 0.6, "pluck": "sync", "drums": "backbeat", "bass": 0.9},
    "ARTISANAL": {"bpm": 92,  "chords": [[55, 59, 62], [50, 54, 57], [52, 55, 59], [48, 52, 55]], "pad": 0.3, "pluck": "finger", "drums": "shaker", "bass": 0.5},
    "MINIMAL":   {"bpm": 70,  "chords": [[48, 52, 55, 59], [45, 48, 52, 55]], "pad": 0.9, "pluck": "sparse", "drums": "none", "bass": 0.4},
}


# ----------------------------------------------------------------------------
# Texto falado
# ----------------------------------------------------------------------------
_UNITS = {"cm": "centímetros", "mm": "milímetros", "m": "metros", "kg": "quilos", "g": "gramas", "ml": "mililitros", "l": "litros"}


def speakable(text: str) -> str:
    """Ajusta a PRONÚNCIA sem mudar o conteúdo: '80x150cm' vira '80 por 150 centímetros'
    (evita ler 'oitenta por cento e cinquenta')."""
    t = text
    t = re.sub(r"(\d+[.,]?\d*)\s*[xX×]\s*(\d+[.,]?\d*)(?:\s*[xX×]\s*(\d+[.,]?\d*))?\s*(cm|mm|m)\b",
               lambda m: " por ".join(g for g in m.groups()[:3] if g) + " " + _UNITS[m.group(4)], t)
    t = re.sub(r"(\d+[.,]?\d*)\s*[xX×]\s*(\d+[.,]?\d*)", r"\1 por \2", t)
    t = re.sub(r"(\d)\s*(cm|mm|kg|ml)\b", lambda m: f"{m.group(1)} {_UNITS[m.group(2)]}", t)
    t = re.sub(r"(\d+)\s*%", r"\1 por cento", t)
    t = re.sub(r"R\$\s*(\d+),(\d{2})", r"\1 reais e \2 centavos", t)
    return " ".join(t.split())


# ----------------------------------------------------------------------------
# I/O de áudio
# ----------------------------------------------------------------------------
def write_wav(path: Path, arr: np.ndarray, sr: int) -> None:
    pcm = (np.clip(arr, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(arr.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def decode_audio(path: Path, sr: int) -> np.ndarray:
    res = run([which_tool("ffmpeg"), "-v", "error", "-i", str(path), "-ar", str(sr), "-ac", "2", "-f", "f32le", "-"])
    return np.frombuffer(res.stdout, dtype="<f4").reshape(-1, 2).copy()


def _stereo(m: np.ndarray, pan: float = 0.0) -> np.ndarray:
    l, r = np.sqrt((1 - pan) / 2) * 1.414, np.sqrt((1 + pan) / 2) * 1.414
    return np.stack([m * l, m * r], axis=1).astype(np.float32)


# ----------------------------------------------------------------------------
# ElevenLabs
# ----------------------------------------------------------------------------
class VoiceNotConfigured(PipelineError):
    pass


def voice_settings(cfg: dict) -> tuple[str, str]:
    e = cfg["elevenlabs"]
    key, vid = os.environ.get(e["api_key_env"]), os.environ.get(e["voice_id_env"])
    if not key or not vid:
        raise VoiceNotConfigured(
            f"ElevenLabs não configurado: defina as variáveis de ambiente {e['api_key_env']} e {e['voice_id_env']}.")
    return key, vid


def enforce_voice_lock(voice_id: str, allow_change: bool = False) -> None:
    """A voz da marca é gravada na primeira vez e não muda sozinha."""
    lock = CONFIG_PATH.parent / "voice.lock.json"
    if lock.exists():
        locked = load_json(lock)["voice_id"]
        if locked != voice_id and not allow_change:
            raise PipelineError(
                f"ELEVENLABS_VOICE_ID ({voice_id}) difere da voz oficial travada ({locked}). Mantenha a mesma voz "
                "da marca ou apague config/voice.lock.json de propósito para trocar.")
    else:
        save_json(lock, {"voice_id": voice_id, "locked_at": iso()})


def tts_elevenlabs(text: str, cfg: dict, cache: Path, logger: Logger, allow_voice_change: bool = False) -> Path:
    """Gera (ou reaproveita do cache) a locução em MP3. Retorna o caminho."""
    import requests
    key, vid = voice_settings(cfg)
    enforce_voice_lock(vid, allow_voice_change)
    e = cfg["elevenlabs"]
    spoken = speakable(text)
    h = hashlib.sha1(json.dumps([spoken, vid, e["model_id"], e["stability"], e["similarity_boost"], e["style"]]).encode()).hexdigest()[:20]
    out = cache / "tts" / f"{h}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {"text": spoken, "model_id": e["model_id"],
            "voice_settings": {"stability": e["stability"], "similarity_boost": e["similarity_boost"], "style": e["style"]}}
    if e.get("language_code") and "v2" not in e["model_id"]:
        body["language_code"] = e["language_code"]
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}", params={"output_format": e["output_format"]},
                      headers={"xi-api-key": key, "Content-Type": "application/json"}, json=body, timeout=90)
    if r.status_code != 200:
        raise PipelineError(f"ElevenLabs HTTP {r.status_code}: {r.text[:300]}")
    tmp = out.with_suffix(".part")
    tmp.write_bytes(r.content)
    os.replace(tmp, out)
    logger.info("locução gerada", chars=len(spoken), voz=vid[:6] + "…")
    return out


# ----------------------------------------------------------------------------
# Síntese de efeitos
# ----------------------------------------------------------------------------
def _t(n, sr):
    return np.arange(n, dtype=np.float32) / sr


def _noise_sweep(dur, sr, f0, f1, width=0.55, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    x = rng.standard_normal(n).astype(np.float32)
    N, hop = 1024, 256
    win = np.hanning(N).astype(np.float32)
    out = np.zeros(n + N, dtype=np.float32)
    freqs = np.fft.rfftfreq(N, 1 / sr)[1:]
    for k, s in enumerate(range(0, n - N, hop)):
        u = s / max(n - N, 1)
        fc = f0 * (f1 / f0) ** u
        g = np.exp(-0.5 * (np.log(freqs / fc) / width) ** 2)
        spec = np.fft.rfft(x[s:s + N] * win)
        spec[1:] *= g
        out[s:s + N] += np.fft.irfft(spec, N) * win
    out = out[:n]
    return out / (np.max(np.abs(out)) + 1e-9)


def synth_sfx(kind: str, sr: int = SR_DEFAULT, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if kind in ("whoosh", "transition"):
        n = _noise_sweep(0.75, sr, 350, 4200, seed=seed)
        env = np.sin(np.linspace(0, np.pi, len(n))) ** 2
        return _stereo(n * env * 0.9)
    if kind == "swipe":
        n = _noise_sweep(0.35, sr, 900, 6500, width=0.5, seed=seed)
        env = np.sin(np.linspace(0, np.pi, len(n))) ** 1.5
        return _stereo(n * env * 0.8)
    if kind in ("impact", "hit", "soft_impact"):
        soft = kind == "soft_impact"
        dur = 0.5 if soft else 0.95
        t = _t(int(dur * sr), sr)
        f = 42 + (95 - 42) * np.exp(-t * 22)
        body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / (0.10 if soft else 0.28))
        burst = rng.standard_normal(len(t)).astype(np.float32)
        burst = np.convolve(burst, np.ones(24) / 24, mode="same") * np.exp(-t / 0.035)
        out = body * 0.9 + burst * 0.5
        return _stereo(out * (0.45 if soft else 0.85))
    if kind == "click":
        t = _t(int(0.12 * sr), sr)
        tick = np.sin(2 * np.pi * 2300 * t) * np.exp(-t / 0.010)
        nb = rng.standard_normal(len(t)).astype(np.float32) * np.exp(-t / 0.002)
        return _stereo((tick * 0.55 + nb * 0.35))
    if kind == "pop":
        t = _t(int(0.28 * sr), sr)
        f = 480 + 700 * np.minimum(t / 0.07, 1.0)
        out = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.07)
        return _stereo(out * 0.6)
    if kind == "rise":
        n = _noise_sweep(1.4, sr, 220, 5200, width=0.7, seed=seed)
        t = _t(len(n), sr)
        f = 220 * (4 ** (t / 1.4))
        tone = np.sin(2 * np.pi * np.cumsum(f) / sr) * 0.25
        env = (t / 1.4) ** 2.2
        return _stereo((n * 0.6 + tone) * env * 0.8)
    if kind == "ambient":
        n = int(3.0 * sr)
        x = np.convolve(rng.standard_normal(n).astype(np.float32), np.ones(200) / 200, mode="same")
        return _stereo(x * 0.05)
    raise PipelineError(f"Efeito sonoro desconhecido: {kind}")


# ----------------------------------------------------------------------------
# Síntese de trilha
# ----------------------------------------------------------------------------
def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _pluck(freq, dur, sr, bright=1.0):
    t = _t(int(dur * sr), sr)
    out = np.zeros_like(t)
    for h, (a, d) in enumerate([(1.0, 0.45), (0.5, 0.25), (0.25, 0.15), (0.12, 0.1)], 1):
        out += a * np.sin(2 * np.pi * freq * h * t) * np.exp(-t / (d * (0.6 + 0.4 * bright)))
    return out * np.minimum(t / 0.004, 1.0)


def _fft_reverb(x, sr, wet=0.25, length=0.9, seed=1):
    rng = np.random.default_rng(seed)
    n = int(length * sr)
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-np.linspace(0, 7, n))
    ir[:int(0.02 * sr)] *= np.linspace(0, 1, int(0.02 * sr))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    y = y / (np.max(np.abs(y)) + 1e-9) * np.max(np.abs(x))
    return x * (1 - wet) + y * wet


def synth_music(profile: str, dur: float, sr: int = SR_DEFAULT, seed: int = 11, bpm: float | None = None,
                energy_pts: list | None = None) -> np.ndarray:
    """Trilha original em camadas (pad, melodia, baixo, percussão). Com `energy_pts` [(t, 0..1)] ela
    CRESCE: começa mínima (pad) e acumula melodia → baixo → percussão até o clímax. Os tempos fortes caem
    em k·(60/bpm) a partir de t=0, então cortes alinhados à grade batem exatamente na batida."""
    p = PROFILES[profile]
    rng = np.random.default_rng(seed)
    n = int((dur + 1.5) * sr)
    beat = 60.0 / (bpm or p["bpm"])
    bar = beat * 4
    pad = np.zeros(n, dtype=np.float32)
    mel = np.zeros(n, dtype=np.float32)
    bass = np.zeros(n, dtype=np.float32)
    drums = np.zeros(n, dtype=np.float32)

    def add(buf, x, at):
        s = int(at * sr)
        if s < n:
            e = min(n, s + len(x))
            buf[s:e] += x[:e - s]

    nbars = int(np.ceil((dur + 1.5) / bar)) + 1
    for b in range(nbars):
        chord = p["chords"][b % len(p["chords"])]
        t0 = b * bar
        # pad
        L = int((bar + 0.6) * sr)
        tt = _t(L, sr)
        env = np.minimum(tt / 0.5, 1.0) * np.minimum((bar + 0.6 - tt) / 0.6, 1.0)
        for note in chord:
            f = _midi(note)
            for det in (-0.004, 0.004):
                w = sum(np.sin(2 * np.pi * f * (1 + det) * h * tt) / h ** 1.6 for h in range(1, 6))
                add(pad, w * env * 0.10 * p["pad"], t0)
        # baixo
        root = _midi(chord[0] - 12)
        steps = {"four": [0, 1, 2, 3], "backbeat": [0, 2.5], "heart": [0], "shaker": [0, 2], "none": [0]}[p["drums"]]
        for s_ in steps:
            tb = _t(int(beat * 0.9 * sr), sr)
            add(bass, (np.sin(2 * np.pi * root * tb) + 0.35 * np.sin(4 * np.pi * root * tb)) * np.exp(-tb / 0.35) * 0.5 * p["bass"], t0 + s_ * beat)
        # melodia
        pat = p["pluck"]
        if pat == "sparse":
            pts = [(0, 0), (1.5, 2), (3, 1)] if b % 2 == 0 else [(0.5, 1), (2.5, 0)]
        elif pat == "arp8":
            pts = [(i * 0.5, i % len(chord)) for i in range(8)]
        elif pat == "arp16":
            pts = [(i * 0.25, (i * 2) % len(chord)) for i in range(16)]
        elif pat == "sync":
            pts = [(0, 0), (0.75, 1), (1.5, 2), (2.25, 1), (3, 0), (3.5, 2)]
        else:  # finger
            pts = [(0, 0), (0.5, 1), (1, 2), (1.5, 1), (2, 0), (2.5, 1), (3, 2), (3.5, 1)]
        for pos, ni in pts:
            note = chord[ni % len(chord)] + 12
            vol = 0.20 * (0.8 + 0.4 * rng.random())
            add(mel, _pluck(_midi(note), 0.9, sr) * vol, t0 + pos * beat)
        # percussão
        d = p["drums"]
        if d in ("four", "backbeat", "heart"):
            for k in ([0, 1, 2, 3] if d == "four" else [0, 2] if d == "backbeat" else [0]):
                tk = _t(int(0.25 * sr), sr)
                f = 45 + 90 * np.exp(-tk * 40)
                add(drums, np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tk / 0.09) * (0.55 if d != "heart" else 0.3), t0 + k * beat)
        if d in ("backbeat",):
            for k in (1, 3):
                tc = _t(int(0.16 * sr), sr)
                nz = np.diff(rng.standard_normal(len(tc) + 1)).astype(np.float32) * np.exp(-tc / 0.04)
                add(drums, nz * 0.25, t0 + k * beat)
        if d in ("four", "shaker"):
            for k in np.arange(0.5 if d == "four" else 0.0, 4, 1.0 if d == "four" else 0.5):
                th = _t(int(0.06 * sr), sr)
                nz = np.diff(rng.standard_normal(len(th) + 1)).astype(np.float32) * np.exp(-th / 0.015)
                add(drums, nz * (0.16 if d == "four" else 0.07), t0 + k * beat)
    mel = _fft_reverb(mel, sr, wet=0.3)
    nout = int(dur * sr)
    layers = {"pad": pad * 0.9, "mel": mel, "bass": bass, "drums": drums}
    if energy_pts:
        t = np.arange(len(pad)) / sr
        ts, es = zip(*energy_pts)
        e = np.interp(t, ts, es)
        k = int(0.6 * sr)
        e = np.convolve(np.pad(e, (k // 2, k - k // 2 - 1), mode="edge"), np.ones(k) / k, mode="valid")[: len(t)]
        sm = lambda x0, x1: np.clip((e - x0) / (x1 - x0), 0, 1) ** 2 * (3 - 2 * np.clip((e - x0) / (x1 - x0), 0, 1))
        gains = {"pad": 0.30 + 0.70 * e, "mel": sm(0.18, 0.60) * (0.4 + 0.6 * e), "bass": sm(0.40, 0.70),
                 "drums": sm(0.66, 0.90)}
        layers = {k_: v * gains[k_] for k_, v in layers.items()}
    mono = sum(layers.values())
    out = _stereo(mono)
    delay = int(0.012 * sr)  # leve abertura estéreo (Haas)
    out[delay:, 1] = out[delay:, 1] * 0.8 + mono[:-delay] * 0.2
    out = out[:nout]
    return out / (np.max(np.abs(out)) + 1e-9) * 0.5


def energy_points(sb: dict) -> list[tuple[float, float]]:
    """Curva de energia da trilha: começa baixa (mais baixa em ritmo lento) e SOBE com o tempo até o máximo no CTA.
    É monotônica de propósito: o ápice da música coincide com o fim do vídeo (revelação/CTA), não com a primeira
    cena de 'produto' — em alguns arquétipos o produto aparece aos 2–3 s e o clímax lá seria cedo demais."""
    sc = sb["scenes"]
    D = sb["total_duration"]
    start = {"slow": 0.12, "medium": 0.20, "fast": 0.36}.get(sb["strategy"].get("pace", "medium"), 0.20)
    pts = []
    for i, s in enumerate(sc):
        u = (s["start"] + s["duration"] * 0.5) / D
        e = start + (0.92 - start) * (u ** 1.15)
        if s["role"] == "CTA" or i == len(sc) - 1:
            e = 1.0
        pts.append((round(s["start"], 3), round(e, 3)))
    pts.append((round(D, 3), 1.0))
    return pts


def synth_texture(kind: str, dur: float, sr: int = SR_DEFAULT, seed: int = 5) -> np.ndarray:
    """Cama sonora contínua e discreta (nunca silêncio). room = ambiente grave; air = sopro agudo; tick = micro cliques."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    x = rng.standard_normal(n).astype(np.float32)
    if kind == "air":
        x = np.convolve(np.diff(x, prepend=0), np.ones(3) / 3, mode="same")
    elif kind == "tick":
        x = np.convolve(x, np.ones(300) / 300, mode="same") * 3
        pos = 0.0
        while pos < dur - 0.05:
            i = int(pos * sr)
            tt = np.arange(int(0.012 * sr)) / sr
            x[i:i + len(tt)] += np.sin(2 * np.pi * 1800 * tt) * np.exp(-tt / 0.002) * 0.35
            pos += rng.uniform(0.28, 0.65)
    else:  # room
        x = np.convolve(x, np.ones(260) / 260, mode="same") * 4
    slow = 0.75 + 0.25 * np.sin(2 * np.pi * rng.uniform(0.15, 0.35) * np.arange(n) / sr + rng.uniform(0, 6.28))
    x = x * slow
    return (x / (np.max(np.abs(x)) + 1e-9)).astype(np.float32)


TEXTURE_FOR_SHOT = {"hero": "room", "hero_wide": "room", "detail": "air", "detail2": "air", "macro": "tick", "macro2": "tick"}


def plan_music(sb: dict, cfg: dict, seed: int) -> dict:
    """Decide a fonte da trilha ANTES do corte final, para travar os cortes na batida (beat-lock)."""
    profile = sb["strategy"]["music_profile"]
    track = find_licensed_track(profile, cfg, seed)
    if track:
        m = re.search(r"(\d{2,3})\s*[-_ ]?bpm", track.stem, re.I)
        return {"source": "arquivo", "file": track.name, "profile": profile, "bpm": float(m.group(1)) if m else None, "tunable": False}
    return {"source": "sintetizada", "profile": profile, "bpm": float(PROFILES[profile]["bpm"]), "tunable": True}


def find_licensed_track(profile: str, cfg: dict, rng_seed: int) -> Path | None:
    d = music_dir(cfg)
    if not d.exists():
        return None
    files = [p for p in d.rglob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac", ".ogg")]
    pl = profile.lower()
    cands = [p for p in files if pl in p.stem.lower() or pl in [x.lower() for x in p.parent.parts]]
    if not cands:
        return None
    cands.sort()
    return cands[rng_seed % len(cands)]


def get_music(profile: str, dur: float, cfg: dict, seed: int, logger: Logger, bpm: float | None = None,
              energy_pts: list | None = None) -> tuple[np.ndarray, dict]:
    sr = cfg["audio"]["sample_rate"]
    track = find_licensed_track(profile, cfg, seed)
    if track:
        arr = decode_audio(track, sr)
        if len(arr) < int(dur * sr):
            arr = np.tile(arr, (int(np.ceil(dur * sr / len(arr))), 1))
        arr = arr[:int(dur * sr)]
        arr = arr / (np.max(np.abs(arr)) + 1e-9) * 0.5
        if energy_pts:  # sem camadas separadas, o "crescendo" é uma rampa de volume suave (−4 dB → 0 dB)
            t = np.arange(len(arr)) / sr
            ts, es = zip(*energy_pts)
            e = np.interp(t, ts, es)
            arr = arr * db(-4.0 * (1 - e))[:, None]
        logger.info("trilha da pasta music/", arquivo=track.name, perfil=profile, bpm=bpm)
        return arr.astype(np.float32), {"source": "arquivo", "file": track.name, "profile": profile, "bpm": bpm,
                                        "arrangement": "rampa de volume"}
    logger.info("trilha sintetizada (original, sem copyright)", perfil=profile, bpm=bpm)
    return synth_music(profile, dur, sr, seed, bpm, energy_pts), {"source": "sintetizada", "profile": profile, "bpm": bpm or PROFILES[profile]["bpm"],
                                                                  "arrangement": "camadas" if energy_pts else "plana"}


# ----------------------------------------------------------------------------
# Mix
# ----------------------------------------------------------------------------
def db(x: float) -> float:
    return 10 ** (x / 20)


def duck_curve(voice: np.ndarray, sr: int, duck_db: float, threshold_db: float = -48.0) -> np.ndarray:
    """Ganho (por amostra) da trilha: 1.0 sem voz, db(duck_db) com voz; ataque 40 ms, soltura 450 ms."""
    mono = np.abs(voice).max(axis=1) if voice.ndim == 2 else np.abs(voice)
    hop = int(0.01 * sr)
    nfr = len(mono) // hop + 1
    pad = np.pad(mono, (0, nfr * hop - len(mono)))
    rms = np.sqrt((pad.reshape(nfr, hop) ** 2).mean(axis=1) + 1e-12)
    gate = (20 * np.log10(rms + 1e-12) > threshold_db).astype(np.float32)
    # um pouco de "hold": mantém abaixado nas pausas curtas entre palavras (≤ 250 ms)
    hold = int(0.25 / 0.01)
    g2 = gate.copy()
    last = -10 ** 9
    for i, v in enumerate(gate):
        if v:
            last = i
        elif i - last <= hold:
            g2[i] = 1.0
    s = np.zeros_like(g2)
    a_att, a_rel = 1 - np.exp(-0.01 / 0.04), 1 - np.exp(-0.01 / 0.45)
    cur = 0.0
    for i, v in enumerate(g2):
        cur += (v - cur) * (a_att if v > cur else a_rel)
        s[i] = cur
    lin = 1.0 - s * (1.0 - db(duck_db))
    xs = (np.arange(nfr) + 0.5) * hop
    return np.interp(np.arange(len(voice)), xs, lin).astype(np.float32)


def build_mix(sb: dict, cfg: dict, voice_clips: dict[int, np.ndarray], logger: Logger, out_wav: Path,
              seed: int = 11) -> dict:
    """voice_clips: {indice_da_cena: array estéreo (n,2)}. Escreve out_wav e devolve o relatório de áudio."""
    a = cfg["audio"]
    sr = a["sample_rate"]
    D = sb["total_duration"]
    N = int(round(D * sr))
    # 1) voz
    voice = np.zeros((N, 2), dtype=np.float32)
    voice_events = []
    for s in sb["scenes"]:
        clip = voice_clips.get(s["index"])
        if clip is None:
            continue
        start = s["start"] + (0.12 if s["role"] == "HOOK" else 0.25)
        i0 = int(start * sr)
        clip = clip * db(a["voice_gain_db"])
        i1 = min(N, i0 + len(clip))
        voice[i0:i1] += clip[:i1 - i0]
        voice_events.append({"scene": s["index"], "start": round(start, 3), "end": round(start + len(clip) / sr, 3),
                             "scene_end": round(s["start"] + s["duration"], 3), "cut": i0 + len(clip) > N})
    has_voice = bool(voice_events)
    if has_voice:
        pk = np.max(np.abs(voice))
        voice = voice / (pk + 1e-9) * 0.8
    # 2) trilha + automação de volume + ducking
    mplan = sb.get("music") or {}
    epts = energy_points(sb)
    music, minfo = get_music(sb["strategy"]["music_profile"], D, cfg, seed, logger, bpm=mplan.get("bpm"), energy_pts=epts)
    if len(music) < N:
        music = np.pad(music, ((0, N - len(music)), (0, 0)))
    music = music[:N] * db(a["music_gain_db"])
    t = np.arange(N) / sr
    auto = np.ones(N, dtype=np.float32)
    cta = [s for s in sb["scenes"] if s["role"] == "CTA"]
    if cta:  # pequena subida de energia na chamada final
        c = cta[-1]
        auto *= (1 + (db(1.5) - 1) * np.clip((t - c["start"]) / 0.6, 0, 1)).astype(np.float32)
    fi, fo = a["fade_in_s"], a["fade_out_s"]
    fade = np.minimum(t / fi, 1.0) * np.minimum((D - t) / fo, 1.0)
    duck = duck_curve(voice, sr, a["duck_db"]) if has_voice else np.ones(N, dtype=np.float32)
    music_final = music * (auto * duck * fade)[:, None]
    # 3) efeitos
    sfx_bus = np.zeros((N, 2), dtype=np.float32)
    sfx_events = []
    for s in sb["scenes"]:
        for ev in s.get("sfx", []):
            at = max(0.0, s["start"] + ev["at"])
            clip = synth_sfx(ev["type"], sr, seed=int(at * 100) + 3) * db(a["sfx_gain_db"])
            i0 = int(at * sr)
            i1 = min(N, i0 + len(clip))
            if i0 < N:
                sfx_bus[i0:i1] += clip[:i1 - i0]
            sfx_events.append({"type": ev["type"], "at": round(at, 3), "scene": s["index"]})
    # 3b) textura contínua + pontes sonoras (J-cut): a cama de cada cena entra ANTES do corte e cruza com a anterior
    tex_bus = np.zeros((N, 2), dtype=np.float32)
    bridges = []
    pre, post = a.get("texture_pre_s", 0.25), 0.22
    tgain = db(a.get("texture_gain_db", -22.0))
    for i, s in enumerate(sb["scenes"]):
        kind = TEXTURE_FOR_SHOT.get(s["camera"]["shot"], "room")
        t0 = s["start"] - (pre if i > 0 else 0.0)
        t1 = s["start"] + s["duration"] + (post if i + 1 < len(sb["scenes"]) else 0.0)
        i0, i1 = max(0, int(t0 * sr)), min(N, int(t1 * sr))
        if i1 <= i0:
            continue
        tex = synth_texture(kind, (i1 - i0) / sr + 0.01, sr, seed=17 + i)[: i1 - i0]
        tt = np.arange(i1 - i0) / sr + i0 / sr
        env = np.clip((tt - t0) / max(pre if i > 0 else 0.05, 1e-3), 0, 1) * np.clip((t1 - tt) / post, 0, 1)
        tex_bus[i0:i1] += _stereo(tex * env * tgain, pan=(-0.2 if i % 2 else 0.2))
        if i > 0:
            bridges.append({"cut": round(s["start"], 3), "texture_start": round(t0, 3), "kind": kind, "lead_s": round(s["start"] - t0, 3)})
    mix = voice + music_final + sfx_bus + tex_bus
    mix *= np.minimum(1.0, (D - t) / 0.25)[:, None]  # fade final curtíssimo contra clique
    pk = np.max(np.abs(mix))
    if pk > 0.98:
        mix = np.tanh(mix * (0.98 / pk) * 1.1) / np.tanh(1.1)
    write_wav(out_wav, mix, sr)
    # 4) relatório: mede o ducking de verdade
    third = N // 3
    rms = lambda x: 20 * np.log10(float(np.sqrt((np.abs(x).max(axis=1)[:] ** 2).mean())) + 1e-9)
    report = {"sample_rate": sr, "duration": D, "music": minfo, "voice_events": voice_events, "sfx_events": sfx_events,
              "bridges": bridges, "beat_lock": bool(mplan.get("locked", False)),
              "music_rms_first_third_db": round(rms(music[:third] * 1.0), 2), "music_rms_last_third_db": round(rms(music[-third:]), 2),
              "has_voice": has_voice, "voice_cut": any(e["cut"] or e["end"] > e["scene_end"] + 0.01 for e in voice_events)}
    if has_voice:
        mask = np.abs(voice).max(axis=1) > 0.02
        mu = np.abs(music_final).max(axis=1)
        if mask.sum() > sr * 0.2 and (~mask).sum() > sr * 0.2:
            r_in, r_out = float(np.sqrt((mu[mask] ** 2).mean())), float(np.sqrt((mu[~mask & (fade > 0.9)] ** 2).mean() + 1e-12))
            v_rms = float(np.sqrt((np.abs(voice).max(axis=1)[mask] ** 2).mean()))
            report["voice_rms_db"] = round(20 * np.log10(v_rms + 1e-9), 2)
            report["music_rms_db_during_voice"] = round(20 * np.log10(r_in + 1e-9), 2)
            report["music_rms_db_without_voice"] = round(20 * np.log10(r_out + 1e-9), 2)
            report["ducking_applied_db"] = round(report["music_rms_db_without_voice"] - report["music_rms_db_during_voice"], 2)
    save_json(out_wav.with_suffix(".json"), report)
    return report


def loudnorm_params(wav: Path, cfg: dict, pre: bool = True) -> dict:
    """Passo 1 do loudnorm (medição). `pre=True` mede DEPOIS do compressor de master (é o que vai ser codificado);
    `pre=False` mede o arquivo como está (usado pelo validador no MP4 final)."""
    ln = cfg["audio"]["loudnorm"]
    chain = (cfg["audio"]["master_compressor"] + "," if pre else "") + \
        f"loudnorm=I={ln['I']}:TP={ln['TP']}:LRA={ln['LRA']}:print_format=json"
    res = run([which_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", str(wav), "-af", chain, "-f", "null", "-"])
    txt = res.stderr.decode("utf-8", "replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", txt, re.S)
    if not m:
        raise PipelineError("Não consegui medir o loudness do áudio.")
    return json.loads(m.group(0))


def loudnorm_filter(measured: dict, cfg: dict) -> str:
    """Cadeia de master: compressor (reduz a diferença entre picos de efeitos e a trilha) → loudnorm linear em
    2 passos (-14 LUFS) → limitador. Sem o compressor, vídeos com picos de efeito não atingiam -14 LUFS e o true
    peak estourava depois do AAC (medido: até +0,9 dBTP); com ele, todos os casos testados ficaram em -14,1…-14,3 LUFS
    e true peak ≤ -1,3 dBTP."""
    a = cfg["audio"]
    ln = a["loudnorm"]
    return (f"{a['master_compressor']},loudnorm=I={ln['I']}:TP={ln['TP']}:LRA={ln['LRA']}:measured_I={measured['input_i']}:"
            f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
            f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true,"
            f"alimiter=limit={a['master_limit']}:attack=5:release=60:level=disabled")
