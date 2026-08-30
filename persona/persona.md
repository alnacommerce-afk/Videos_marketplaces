# Modelo-UGC-1

Persona (criadora) padrão usada em todos os vídeos UGC dos marketplaces (Mercado Livre, Shopee, TikTok Shop, Temu, Amazon). Mesmo rosto e mesma voz em todos os vídeos, para manter consistência de marca.

- **Imagem de referência (identidade fixa):** ![Modelo-UGC-1](https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/1bce158d-fb59-440a-8c22-05b12ecff807.png)
- **Origem:** foto enviada pelo usuário — confirmado que é imagem gerada por IA (não retrata pessoa real), então sem bloqueio de autorização.
- **media_id de referência (character_media_id):** `1bce158d-fb59-440a-8c22-05b12ecff807`
- **Voz padrão:** Ainsley (preset, feminina) — `voice_id: 731b4ffe-e95e-59f4-8c00-81608936091f`
  - Preview: https://d1xarpci4ikg0w.cloudfront.net/audio_voice/731b4ffe-e95e-59f4-8c00-81608936091f/preview-37d345ad8f2edf91.mp3

## Regras de produção fixas

- **Idioma: sempre português do Brasil.** Todo roteiro/monólogo é escrito em pt-BR (nunca em inglês, mesmo sendo o default do workflow).
- **Sincronia labial obrigatória.** A modelo sempre fala em cena, nunca narração em off; a fala nativa do modelo de vídeo é gerada diretamente a partir do roteiro em pt-BR, garantindo lip-sync correto desde a geração.
- **Voz travada:** depois do vídeo renderizado, roda `voice_change` (voice_id da Ainsley, voice_type=preset) pra garantir que a voz final é sempre a mesma, mantendo timing/visual do vídeo.

## Como a consistência é garantida

1. **Rosto:** essa mesma imagem de referência (`character_media_id` = media_id acima) é reaproveitada em todos os boards/clipes de todos os vídeos, em todas as plataformas — nunca é regenerada.
2. **Voz:** primeiro a fala nativa é gerada em pt-BR (pra garantir sincronia labial certa com o português); depois `voice_change` trava o áudio final na voz Ainsley.

## Histórico

- Primeira versão da persona foi gerada por IA internamente e **rejeitada pelo usuário**.
- Versão atual: foto enviada pelo usuário (`1bce158d-fb59-440a-8c22-05b12ecff807`), confirmada como imagem de IA (não pessoa real).

## Regras de uso

- Sempre passar o `media_id` acima como `character_media_id` ao workflow `ugc-review-video` para qualquer novo vídeo.
- Sempre escrever o roteiro em português do Brasil.
- Sempre aplicar `voice_change` com a voz Ainsley no vídeo final antes da entrega.
- Roteiro muda por plataforma (ver `platforms/<plataforma>/scripts/`), mas rosto, voz e idioma permanecem fixos.
