# python-video

Pipeline alternativo de criação de vídeo pra marketplaces, separado do pipeline principal
do repositório (que usa Higgsfield + IA generativa — ver `persona/` e `platforms/`).

Esse pipeline monta vídeo programaticamente (Python/ffmpeg/moviepy), sem gastar crédito de
geração de IA. Ainda sem formato definido — ver `.claude/skills/python-video/SKILL.md` pra
status e perguntas pendentes.

## Estrutura

- `scripts/` — código Python/ffmpeg reaproveitável
- `templates/` — templates/funções reaproveitáveis (zoom, overlay de texto, etc.)
- `output/` — vídeos finais gerados por esse pipeline
