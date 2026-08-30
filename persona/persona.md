# Modelo-UGC-1

Persona (criadora) padrão usada em todos os vídeos UGC dos marketplaces (Mercado Livre, Shopee, TikTok Shop, Temu, Amazon). Mesmo rosto e mesma voz em todos os vídeos, para manter consistência de marca.

- **Imagem de referência (identidade fixa):** ![Modelo-UGC-1](https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20260830_134749_3ef31ac9-10a7-4ff3-92b5-4711f51c29ee.png)
- **job_id de referência (character_media_id):** `3ef31ac9-10a7-4ff3-92b5-4711f51c29ee`
- **Voz padrão:** Ainsley (preset, feminina) — `voice_id: 731b4ffe-e95e-59f4-8c00-81608936091f`
  - Preview: https://d1xarpci4ikg0w.cloudfront.net/audio_voice/731b4ffe-e95e-59f4-8c00-81608936091f/preview-37d345ad8f2edf91.mp3

## Como a consistência é garantida

1. **Rosto:** essa mesma imagem de referência (`character_media_id`) é reaproveitada em todos os boards/clipes de todos os vídeos, em todas as plataformas — nunca é regenerada.
2. **Voz:** o modelo de vídeo (Seedance 2.5) gera fala nativa sincronizada aos lábios, mas essa fala nativa varia a cada geração. Para travar sempre na mesma voz (Ainsley), rodamos `voice_change` no vídeo final de cada plataforma, substituindo o áudio gerado pela voz Ainsley mantendo o lip-sync e o timing originais.

## Traços da persona

- Mulher, ~mid 20s, feições equilibradas, estilo clean-minimalist / casual
- Cabelo castanho claro, ondulado, comprido
- Sardas leves, maquiagem natural do dia a dia
- Visual versátil (não travado a um nicho específico), pensado para funcionar bem com categorias variadas de produto (casa, beleza, tech, moda etc.)
- Acessório de assinatura: bracelete largo prateado

## Regras de uso

- Sempre passar `character_reference.job_id` como referência de identidade (`character_media_id`) ao workflow `ugc-review-video` para qualquer novo vídeo.
- Sempre aplicar `voice_change` com `voice_id` da Ainsley no vídeo final antes da entrega.
- Roteiro/script muda por plataforma (ver `platforms/<plataforma>/scripts/`), mas rosto e voz permanecem fixos.
