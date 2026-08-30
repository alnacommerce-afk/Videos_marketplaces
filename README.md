# Videos Marketplaces

Geração de vídeos UGC (creator falando pra câmera) para anúncios em marketplaces, usando Higgsfield.ai. Uma persona e uma voz padrão (`Modelo-UGC-1`, voz Ainsley) aparecem em todos os vídeos — o que muda por plataforma é o roteiro, seguindo as políticas de cada uma.

## Plataformas

- Mercado Livre — `platforms/mercado_livre/`
- Shopee — `platforms/shopee/`
- TikTok Shop — `platforms/tiktok_shop/`
- Temu — `platforms/temu/`
- Amazon — `platforms/amazon/`

Cada pasta tem:
- `policy.md` — resumo das políticas de vídeo/anúncio da plataforma (duração, conteúdo permitido/proibido, formato etc.)
- `scripts/` — um roteiro por produto/vídeo gerado para aquela plataforma

## Persona padrão

Ver `persona/persona.md` — rosto e voz fixos, reaproveitados em todo vídeo novo.

## Pipeline por vídeo

1. Produto: foto(s) ou URL do anúncio.
2. Roteiro adaptado à política da plataforma-alvo (duração, claims permitidos, disclosure de publi etc.).
3. Geração do vídeo UGC (Higgsfield `ugc-review-video`), usando sempre o `character_media_id` da Modelo-UGC-1.
4. `voice_change` no vídeo final para travar a voz na Ainsley.
5. Entrega: link do vídeo hospedado + download.

## Status

Persona criada. Aguardando: políticas de cada plataforma e o primeiro produto para gerar o vídeo piloto.
