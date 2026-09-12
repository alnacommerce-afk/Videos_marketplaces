# Tábua de Cortar Carne — Shopee (15s)

- Persona: Modelo-UGC-1 (`persona/persona.md`), aparece em cena mas **não fala** (modo narração em off)
- Voz: Ainsley, motor ElevenLabs (`text2speech_v2`/`variant: elevenlabs`) — locução travada, sem restrição de sincronia labial
- Idioma: português do Brasil
- Duração: 15s, vídeo único
- Fotos do produto (reais, enviadas pelo usuário): `media_id 6d25f7a1-5fe3-4649-8907-cd5927058a59`, `94cd34cd-5295-41d7-b02d-76fa6253b5b8`, `0c6e1bee-c147-41b8-bf8e-d55c2528f568`, `904b628d-247c-4845-ad86-ef744faa5a6e`

## Locução (voz off) — versão final corrigida

> Essa tábua de cortar carne é daquelas que muda a rotina na cozinha. Bem grande, resistente, lisa e reta dos dois lados, dá pra usar dos dois lados sem problema. Fácil de limpar depois do uso e ainda deixa qualquer bancada mais bonita.

(Versão inicial mencionava um "sulco nas bordas pra segurar o suco da carne" — **característica inventada que não existe na tábua real**. O usuário confirmou que a tábua é lisa e reta dos dois lados, sem sulco/borda. Corrigido: roteiro reescrito e storyboard/vídeo regenerados com as fotos reais do produto como referência.)

## Arco (8 cenas) — versão final

1. Selfie — segura a tábua perto do rosto, admirando.
2. Estático wide — apoia a tábua na bancada da cozinha.
3. Estático macro — dedos deslizando na superfície, mostrando o acabamento real.
4. Selfie tight — tábua perto do rosto, sorriso genuíno (boca fechada).
5. Estático — vira a tábua mostrando que o outro lado é igualmente liso (sem sulco).
6. Estático macro — detalhe da borda reta e da espessura real.
7. Estático wide — levanta a tábua e apresenta pra câmera (pico).
8. Selfie tight — fecha com a tábua junto ao corpo, sorriso confiante.

## Pipeline usado (modo narração em off, sem lip-sync)

1. Storyboard gerado com o rosto da Modelo-UGC-1 sempre de boca fechada/neutra (nunca falando), usando as 4 fotos reais da tábua como referência de ângulo/material (não apenas 1 foto, para reduzir erro de detalhe).
2. Vídeo gerado **silencioso** (`generate_audio: false`) — só imagem, sem áudio nativo.
3. Locução gerada à parte via ElevenLabs (voz Ainsley), sem a característica inventada.
4. Vídeo silencioso + locução mixados via ffmpeg (sandbox), convertido pra H.264.

## Entregáveis

### Versão final (usar esta)

- Storyboard corrigido: https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260912_002456_1bfd6fd7-77f0-48fa-8465-622cc557025b.png
- Locução corrigida (ElevenLabs, Ainsley): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260912_001902_dd68316f-6021-4bb0-9ac3-fdfbcb4fb9f0.mp3
- **Vídeo final (H.264, com locução corrigida):** https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/b7030310-9988-4d6d-a8ea-9a6b294f3f71.mp4

### Versões anteriores (histórico, com erro — não usar)

- v1: storyboard/vídeo com sulco inventado — https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260912_000900_fd5c49a7-908c-4d22-ac46-bcab291b0ef2.png
- v1 vídeo final (com erro): https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/4cbac6ba-42c7-453c-a06f-86203337d79b.mp4

## Observação

Nenhuma política oficial da Shopee foi fornecida ainda — roteiro evita alegações não verificáveis. **Lição aprendida:** o agente não consegue visualizar imagens enviadas pelo usuário diretamente (só recebe o `media_id`), então nunca deve inventar características físicas do produto (textura, sulco, encaixe etc.) — sempre usar apenas o que o usuário descreveu por texto, e deixar a imagem de referência informar a aparência real só para o modelo de geração (que sim enxerga a imagem), nunca para o texto do roteiro.
