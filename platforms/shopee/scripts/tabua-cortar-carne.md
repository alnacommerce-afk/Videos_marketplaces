# Tábua de Cortar Carne — Shopee (15s)

- Persona: Modelo-UGC-1 (`persona/persona.md`), aparece em cena mas **não fala** (modo narração em off)
- Voz: Ainsley, motor ElevenLabs (`text2speech_v2`/`variant: elevenlabs`) — locução travada, sem restrição de sincronia labial
- Idioma: português do Brasil
- Duração: 15s, vídeo único
- Foto do produto: `media_id a1b6813e-60e5-449f-995b-71e87ec7dd1b`

## Locução (voz off)

> Essa tábua de cortar carne é daquelas que muda a rotina na cozinha. Bem grande, resistente, com um sulco nas bordas que segura o suco da carne e não deixa escorrer pra fora. Fácil de limpar depois do uso e ainda deixa qualquer bancada mais bonita.

## Arco (8 cenas)

1. Selfie — segura a tábua perto do rosto, admirando.
2. Estático wide — apoia a tábua na bancada da cozinha.
3. Estático macro — dedos deslizando na superfície, mostrando o acabamento.
4. Selfie tight — tábua perto do rosto, sorriso genuíno (boca fechada).
5. Estático — vira a tábua mostrando o sulco/verso.
6. Estático macro — detalhe do sulco/borda.
7. Estático wide — levanta a tábua e apresenta pra câmera (pico).
8. Selfie tight — fecha com a tábua junto ao corpo, sorriso confiante.

## Pipeline usado (modo narração em off, sem lip-sync)

1. Storyboard gerado com o rosto da Modelo-UGC-1 sempre de boca fechada/neutra (nunca falando).
2. Vídeo gerado **silencioso** (`generate_audio: false`) — só imagem, sem áudio nativo.
3. Locução gerada à parte via ElevenLabs (voz Ainsley).
4. Vídeo silencioso + locução mixados via ffmpeg (sandbox), convertido pra H.264.

## Entregáveis

- Storyboard: https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260912_000900_fd5c49a7-908c-4d22-ac46-bcab291b0ef2.png
- Vídeo silencioso (bruto): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260912_001022_ec45e879-715c-4c30-b522-916331094855.mp4
- Locução (ElevenLabs, Ainsley): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260912_001032_4a76a77c-1410-4137-8468-a999a5a07528.mp3
- **Vídeo final (H.264, com locução):** https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/4cbac6ba-42c7-453c-a06f-86203337d79b.mp4

## Observação

Nenhuma política oficial da Shopee foi fornecida ainda — roteiro evita alegações não verificáveis (não afirma material específico, já que não pôde ser confirmado visualmente pelo agente; a imagem de referência é que define a aparência real do produto no vídeo).
