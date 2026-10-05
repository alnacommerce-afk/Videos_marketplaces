"""Biblioteca de efeitos sonoros com ElevenLabs (gera UMA vez e reutiliza: custo baixo e som consistente entre vídeos).

Cria sfx\\<tipo>.mp3 para os efeitos que o pipeline usa (whoosh, swipe, soft_impact, click, pop, rise). Quando o arquivo existe,
`audio.synth_sfx` usa o arquivo; sem ele, continua usando o som sintetizado (nada quebra). Efeitos gerados na API do ElevenLabs
têm licença comercial nos planos pagos. Música: NÃO usamos a geração de música do ElevenLabs sem conferir a licença do seu plano
para publicidade (a música tem licença adicional para anúncios).

  python elevenlabs_sfx.py generate [--force]     # gera a biblioteca (1 chamada por tipo)
  python elevenlabs_sfx.py list
Chave: API\\APIelevenlabs.txt (a mesma da narração).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from common import SKILL_DIR, Logger, PipelineError, load_config, redact
from localsecrets import eleven_credentials

SFX_DIR = SKILL_DIR / "sfx"
PROMPTS = {  # tipo -> (descrição em inglês para a API, duração em segundos)
    "whoosh": ("fast clean cinematic whoosh transition, no music, no voice", 0.9),
    "swipe": ("short soft swipe sound, quick air movement, no music", 0.5),
    "soft_impact": ("soft low thud impact, subtle, clean, no reverb tail", 0.7),
    "click": ("single crisp UI click, modern, short", 0.3),
    "pop": ("playful bubble pop, bright, short", 0.4),
    "rise": ("short rising tension riser, clean, no music, no voice", 1.2),
}


def generate_one(kind: str, cfg: dict, key: str, logger: Logger) -> Path:
    base = cfg["elevenlabs"].get("api_base", "https://api.elevenlabs.io").rstrip("/")
    text, dur = PROMPTS[kind]
    try:
        r = requests.post(f"{base}/v1/sound-generation", params={"output_format": cfg["elevenlabs"].get("output_format", "mp3_44100_128")},
                          headers={"xi-api-key": key, "Content-Type": "application/json"},
                          json={"text": text, "duration_seconds": dur, "prompt_influence": 0.5, "model_id": "eleven_text_to_sound_v2"}, timeout=90)
    except requests.RequestException as e:
        raise PipelineError(redact(f"ElevenLabs inacessível: {e}")) from e
    if r.status_code >= 400:
        raise PipelineError(redact(f"ElevenLabs sound-generation {kind}: HTTP {r.status_code} {r.text[:200]}"))
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    out = SFX_DIR / f"{kind}.mp3"
    out.write_bytes(r.content)
    logger.info("efeito gerado", tipo=kind, bytes=len(r.content))
    return out


def generate_all(cfg: dict, logger: Logger, force: bool = False) -> list[str]:
    key, _ = eleven_credentials(cfg)
    if not key:
        raise PipelineError("sem chave do ElevenLabs: crie API\\APIelevenlabs.txt")
    done = []
    for kind in PROMPTS:
        if (SFX_DIR / f"{kind}.mp3").exists() and not force:
            continue
        generate_one(kind, cfg, key, logger)
        done.append(kind)
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Biblioteca de efeitos sonoros (ElevenLabs)")
    ap.add_argument("cmd", choices=["generate", "list"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    cfg, log = load_config(), Logger("sfx")
    try:
        if a.cmd == "list":
            print("\n".join(f"{k}: {'OK' if (SFX_DIR / (k + '.mp3')).exists() else 'sintetizado'}" for k in PROMPTS))
            return 0
        done = generate_all(cfg, log, a.force)
        print(f"Gerados: {', '.join(done) or 'nenhum (já existiam; use --force para refazer)'}")
        return 0
    except PipelineError as e:
        log.error(str(e)[:300])
        return 1


if __name__ == "__main__":
    sys.exit(main())
