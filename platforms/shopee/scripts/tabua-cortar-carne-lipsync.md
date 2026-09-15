# Tábua de Cortar Carne — Shopee (15s) — versão com sincronia labial

- Persona: Modelo-UGC-1, falando em cena (sincronia labial nativa, não é modo narração em off)
- Voz: gerada nativamente pelo Seedance a partir do roteiro (não é a Ainsley/ElevenLabs — trade-off aceito para ter lip-sync real, ver `persona/persona.md`)
- Idioma: português do Brasil
- Duração: 15s
- Fotos do produto (reais): `media_id 6d25f7a1-5fe3-4649-8907-cd5927058a59`, `94cd34cd-5295-41d7-b02d-76fa6253b5b8`, `0c6e1bee-c147-41b8-bf8e-d55c2528f568`, `904b628d-247c-4845-ad86-ef744faa5a6e`

## Roteiro (falado)

> Essa tábua de cortar carne é daquelas que muda a rotina na cozinha. Bem grande, resistente, lisa e reta dos dois lados, dá pra usar tranquilo dos dois lados. Fácil de limpar depois do uso e ainda deixa a bancada mais bonita.

(Sem características inventadas — tábua lisa e reta, confirmado pelo usuário.)

## Status: PENDENTE — sem créditos suficientes

- Storyboard já gerado e aprovado (de-slop feito): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260915_140620_06b76830-10b9-4932-8bdf-10d9e644a3e5.png
- `board_media_id` pra reaproveitar na geração do vídeo: `06b76830-10b9-4932-8bdf-10d9e644a3e5`
- Vídeo (seedance_2_5, 1080p, 15s, omni_reference) custa **135 créditos**; conta tinha **112,86** no momento da tentativa (2026-09-15).
- Usuário optou por esperar recarregar os créditos antes de gerar o vídeo.

## Próximo passo (quando houver créditos)

Rodar `generate_video_batch` com:
- `model: seedance_2_5`, `duration: 15`, `aspect_ratio: 9:16`, `resolution: 1080p`, `mode: omni_reference`, `generate_audio: true`
- `medias`: board (`06b76830-10b9-4932-8bdf-10d9e644a3e5`), character (`1bce158d-fb59-440a-8c22-05b12ecff807`), product (`6d25f7a1-5fe3-4649-8907-cd5927058a59`)
- Depois: baixar, converter pra H.264 (ffmpeg) e entregar.
