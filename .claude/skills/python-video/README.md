# python-video

Pipeline independente (Python + FFmpeg, sem IA generativa) que gera vídeos comerciais 9:16 de 15–18 s a partir das fotos e dos fatos **confirmados** dos produtos ALNA. Documentação completa em [`SKILL.md`](SKILL.md).

Início rápido (Windows): `powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1`
Início rápido (qualquer SO): `pip install -r requirements.txt` → `python tests/test_pipeline.py --fast` → `python scripts/build_video.py --catalog templates/catalog.example.json --voice off`

Manutenção:
- Novo arquétipo: edite `config/archetypes.json` (beats + `requires`); não precisa mexer em código.
- Novo estilo visual: `templates/styles.json`. Novo formato: `config/config.json > formats`.
- Nova checagem de qualidade: `scripts/validator.py` (cada `c.add(...)` é uma checagem; `severity="warn"` não reprova).
- Testes: `python tests/test_pipeline.py` (completo, renderiza vídeos) ou `--fast`.
- Dados gerados (`work/`, `cache/`, `output/`, `logs/*.jsonl`) ficam fora do git (`.gitignore`).
