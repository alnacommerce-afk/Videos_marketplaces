# Modelo-UGC-1

Persona (criadora) padrão usada em todos os vídeos UGC dos marketplaces (Mercado Livre, Shopee, TikTok Shop, Temu, Amazon). Mesmo rosto em todos os vídeos, para manter consistência de marca.

- **Imagem de referência (identidade fixa):** ![Modelo-UGC-1](https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/1bce158d-fb59-440a-8c22-05b12ecff807.png)
- **Origem:** foto enviada pelo usuário — confirmado que é imagem gerada por IA (não retrata pessoa real), então sem bloqueio de autorização.
- **media_id de referência (character_media_id):** `1bce158d-fb59-440a-8c22-05b12ecff807`
- **Voz padrão (quando NÃO precisa lip-sync, ex: narração em off):** Ainsley (preset, feminina) — `voice_id: 731b4ffe-e95e-59f4-8c00-81608936091f`, motor ElevenLabs (`text2speech_v2`/`variant: elevenlabs`)
  - Preview: https://d1xarpci4ikg0w.cloudfront.net/audio_voice/731b4ffe-e95e-59f4-8c00-81608936091f/preview-37d345ad8f2edf91.mp3

## Pergunta obrigatória antes de gerar QUALQUER vídeo novo

Sempre perguntar ao usuário: **esse vídeo vai ter a modelo falando em cena (precisa sincronia labial) ou vai ser narração em voz off (sem a modelo falando na câmera)?**

Isso muda o pipeline:

### A) Modelo falando em cena (lip-sync obrigatório)

- Gerar o vídeo com o `seedance_2_5` deixando o PRÓPRIO modelo criar a fala junto com o vídeo (`mode: omni_reference`, `generate_audio: true`, roteiro pt-BR embutido direto no prompt, na seção "Audio"). É o ÚNICO jeito confiável de sincronia labial real no momento.
- **Não usar** `audio_references` com um áudio pronto (ex: ElevenLabs) esperando que o vídeo sincronize a boca com ele — TESTADO e CONFIRMADO que isso não sincroniza a boca, o Seedance trata esse áudio só como referência de timbre/estilo, não como guia labial.
- **Não usar** `voice_change` pós-render pra trocar a voz nesse caso — ele só troca o áudio "mantendo o timing e o visual original", ou seja, não regenera a boca pra bater com a nova voz; o resultado fica dessincronizado.
- Consequência prática: quando a modelo fala em cena, a voz é a que o próprio Seedance gera nativamente a partir do roteiro (não dá pra travar 100% na voz Ainsley/ElevenLabs sem quebrar a sincronia labial, com as ferramentas disponíveis hoje). Se isso for um problema, avisar o usuário e considerar buscar uma ferramenta de dublagem/lip-sync dedicada antes de prosseguir.

### B) Narração em voz off (sem a modelo falando na câmera)

- A modelo pode aparecer em cena (mostrando o produto, expressões, gestos) mas sem falar / sem boca em foco falando.
- Aí sim: gerar o áudio à parte com `generate_audio` (`text2speech_v2`, `variant: elevenlabs`, voz Ainsley) e usar como voz padrão consistente em todos os vídeos desse tipo, sem se preocupar com sincronia labial.
- Workflow mais adequado nesse caso: `ugc-product-video` (produto é o foco, sem lip-sync) em vez de `ugc-review-video`.

## Regras de produção fixas

- **Idioma: sempre português do Brasil.** Todo roteiro/monólogo é escrito em pt-BR (nunca em inglês, mesmo sendo o default do workflow).
- **Escrita clara, sem ambiguidade.** Evitar armadilhas de leitura em pt-BR — o erro mais comum é escrever dimensões como "80x150" na forma "oitenta por cento e cinquenta" (soa como porcentagem). Preferir "oitenta centímetros de largura por um metro e cinquenta de comprimento". Revisar sempre números, siglas e medidas antes de mandar pro áudio.
- **Conversão de codec obrigatória antes de entregar.** O Higgsfield entrega o vídeo final em HEVC/H.265 — muitos navegadores e apps só tocam o áudio, sem imagem, nesse codec. Sempre baixar o vídeo final via `sandbox_exec`, converter pra H.264 com ffmpeg (`-c:v libx264 -profile:v high -level 4.1 -pix_fmt yuv420p -c:a aac -movflags +faststart`), subir de novo (`media_upload` + `media_confirm`) e entregar esse link H.264 como o definitivo.

## Como a consistência é garantida

1. **Rosto:** essa mesma imagem de referência (`character_media_id` = media_id acima) é reaproveitada em todos os boards/clipes de todos os vídeos, em todas as plataformas — nunca é regenerada.
2. **Voz:** depende do modo (ver seção acima). Narração em off = sempre ElevenLabs/Ainsley, 100% consistente. Modelo falando em cena = voz nativa do Seedance por vídeo (pode variar levemente entre renders), priorizando sincronia labial correta.

## Histórico

- Primeira versão da persona foi gerada por IA internamente e **rejeitada pelo usuário**.
- Versão atual: foto enviada pelo usuário (`1bce158d-fb59-440a-8c22-05b12ecff807`), confirmada como imagem de IA (não pessoa real).
- Primeiro vídeo piloto (Toalha Rubi, Shopee), v1: fala pouco fluente/confusa em pt-BR. Causa: frase ambígua no roteiro ("oitenta por cento e cinquenta") + motor de voz padrão do `voice_change` menos natural em português.
- v2: tentativa de usar áudio ElevenLabs como `audio_references` na geração do vídeo — áudio ficou ótimo, mas **sem sincronia labial** (confirmado pelo usuário). Causa raiz: `audio_references` no Seedance não faz lip-sync real, só influencia timbre/estilo.
- v3 (em teste): geração 100% nativa (Seedance gera fala e vídeo juntos a partir do roteiro corrigido em pt-BR), pra garantir sincronia labial real — trade-off é não travar 100% na voz Ainsley/ElevenLabs quando a modelo fala em cena.
- Também identificado e corrigido: vídeos saíam em HEVC/H.265, tocando só áudio em vários navegadores — agora sempre convertidos pra H.264 antes de entregar.

## Regras de uso

- Sempre passar o `media_id` acima como `character_media_id` ao workflow `ugc-review-video` para qualquer novo vídeo.
- Sempre escrever o roteiro em português do Brasil, revisado contra ambiguidades de leitura.
- Sempre perguntar antes de gerar: modelo fala em cena (lip-sync) ou narração em off (voz ElevenLabs travada)?
- Roteiro muda por plataforma (ver `platforms/<plataforma>/scripts/`), mas rosto e idioma permanecem fixos; a voz é fixa (Ainsley/ElevenLabs) só no modo narração em off.
