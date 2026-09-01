# Modelo-UGC-1

Persona (criadora) padrão usada em todos os vídeos UGC dos marketplaces (Mercado Livre, Shopee, TikTok Shop, Temu, Amazon). Mesmo rosto e mesma voz em todos os vídeos, para manter consistência de marca.

- **Imagem de referência (identidade fixa):** ![Modelo-UGC-1](https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/1bce158d-fb59-440a-8c22-05b12ecff807.png)
- **Origem:** foto enviada pelo usuário — confirmado que é imagem gerada por IA (não retrata pessoa real), então sem bloqueio de autorização.
- **media_id de referência (character_media_id):** `1bce158d-fb59-440a-8c22-05b12ecff807`
- **Voz padrão:** Ainsley (preset, feminina) — `voice_id: 731b4ffe-e95e-59f4-8c00-81608936091f`
  - Preview: https://d1xarpci4ikg0w.cloudfront.net/audio_voice/731b4ffe-e95e-59f4-8c00-81608936091f/preview-37d345ad8f2edf91.mp3

## Regras de produção fixas

- **Idioma: sempre português do Brasil.** Todo roteiro/monólogo é escrito em pt-BR (nunca em inglês, mesmo sendo o default do workflow).
- **Escrita clara, sem ambiguidade.** Evitar armadilhas de leitura em pt-BR — o erro mais comum é escrever dimensões como "80x150" na forma "oitenta por cento e cinquenta" (soa como porcentagem). Preferir "oitenta centímetros de largura por um metro e cinquenta de comprimento". Revisar sempre números, siglas e medidas antes de mandar pro áudio.
- **Motor de voz travado: ElevenLabs.** Testado A/B com o usuário (ElevenLabs vs. motor padrão/seed_audio) — ElevenLabs soou muito mais fluente e natural em pt-BR. Sempre gerar a fala via `generate_audio` com `model: text2speech_v2`, `variant: elevenlabs`, `voice_type: preset`, `voice_id` da Ainsley.
- **Sincronia labial obrigatória.** A modelo sempre fala em cena, nunca narração em off.

## Pipeline de voz (atualizado)

1. Gerar o áudio da fala em pt-BR primeiro: `generate_audio` (`text2speech_v2`, `variant: elevenlabs`, voz Ainsley) a partir do roteiro final já revisado.
2. Gerar o clipe de vídeo (`seedance_2_5`, `mode: omni_reference`) passando esse áudio como referência (`role: audio_references`), junto com o board e o `character_media_id`, instruindo no prompt que os lábios devem seguir exatamente esse áudio (mesmas palavras, mesmo timing) em vez de gerar fala nova.
3. Isso substitui a etapa antiga de `voice_change` pós-render, que usava um motor de fala menos fluente em português — usar `voice_change` só como alternativa de emergência se `audio_references` não estiver disponível.
4. **Conversão de codec obrigatória antes de entregar.** O Higgsfield entrega o vídeo final em HEVC/H.265 — muitos navegadores e apps só tocam o áudio, sem imagem, nesse codec. Sempre baixar o vídeo final via `sandbox_exec`, converter pra H.264 com ffmpeg, subir de novo (`media_upload` + `media_confirm`) e entregar esse link H.264 como o definitivo.

## Como a consistência é garantida

1. **Rosto:** essa mesma imagem de referência (`character_media_id` = media_id acima) é reaproveitada em todos os boards/clipes de todos os vídeos, em todas as plataformas — nunca é regenerada.
2. **Voz:** o áudio é sempre gerado primeiro via ElevenLabs (voz Ainsley) e o vídeo é gerado lendo os lábios exatamente daquele áudio — garante fluência em pt-BR e a mesma voz sempre.

## Histórico

- Primeira versão da persona foi gerada por IA internamente e **rejeitada pelo usuário**.
- Versão atual: foto enviada pelo usuário (`1bce158d-fb59-440a-8c22-05b12ecff807`), confirmada como imagem de IA (não pessoa real).
- Primeiro vídeo piloto (Toalha Rubi, Shopee) veio com fala pouco fluente/confusa em pt-BR. Causa: (a) frase ambígua no roteiro ("oitenta por cento e cinquenta") e (b) motor de voz padrão do `voice_change` menos natural em português. Corrigido: roteiro reescrito + pipeline trocado pra usar áudio ElevenLabs como referência de lip-sync direto na geração do clipe.

## Regras de uso

- Sempre passar o `media_id` acima como `character_media_id` ao workflow `ugc-review-video` para qualquer novo vídeo.
- Sempre escrever o roteiro em português do Brasil, revisado contra ambiguidades de leitura.
- Sempre gerar o áudio via ElevenLabs (voz Ainsley) primeiro e usar como `audio_references` na geração do vídeo.
- Roteiro muda por plataforma (ver `platforms/<plataforma>/scripts/`), mas rosto, voz e idioma permanecem fixos.
