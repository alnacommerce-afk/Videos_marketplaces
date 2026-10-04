---
name: python-video
description: >
  Pipeline alternativo (sem IA generativa) pra criar vídeos de produto pra marketplaces
  usando código Python (ffmpeg/moviepy/Pillow) em vez do pipeline Higgsfield baseado em IA
  (persona/ e platforms/). Use quando o usuário pedir explicitamente "vídeo com python",
  "/python-video", ou um vídeo montado programaticamente (fotos reais + zoom/transições +
  texto + música) sem gerar modelo/avatar por IA. NÃO é o pipeline padrão do repositório —
  só entra em ação quando chamado por esse nome.
---

# python-video

Pipeline separado e independente do pipeline principal do repositório (`persona/` +
`platforms/`, que usa a Higgsfield pra gerar vídeos com a Modelo-UGC-1 por IA). Este aqui
monta vídeo programaticamente, sem gastar crédito de geração de IA — bom pra quando o
produto já tem fotos/vídeos reais prontos e só precisa de montagem (zoom, texto, transição,
trilha).

## Status: AGUARDANDO ESPECIFICAÇÃO

Ainda não tem formato definido. **Antes de escrever qualquer código, pergunte ao usuário**
(se ainda não tiver essa resposta na conversa):

1. Que tipo de vídeo exatamente? (ex: slideshow com zoom tipo Ken Burns nas fotos do
   produto, corte de clipes de vídeo que o usuário já tem, texto animado sobre as fotos,
   etc.)
2. Tem áudio/trilha? Música de fundo, locução gravada, ou silêncio?
3. Duração e proporção (9:16 pra Shopee/TikTok, etc. — mesma lógica de plataforma do
   pipeline principal)?
4. Ferramenta preferida: `moviepy` (mais simples, Python puro) ou `ffmpeg` direto via
   `subprocess`/shell (mais rápido, mais controle)?

Não assuma nenhuma dessas respostas — eram elas que o usuário ia "ensinar" depois.

## Onde os arquivos ficam

- Scripts/código: `python_video/scripts/`
- Templates reaproveitáveis (ex: função de zoom, overlay de texto): `python_video/templates/`
- Saída final dos vídeos: `python_video/output/`
- Documentação de cada vídeo gerado: igual ao padrão do pipeline principal
  (`platforms/<plataforma>/scripts/*.md`), mas aqui pode ficar em
  `python_video/<plataforma>/*.md` se fizer sentido separar.

## Regras que valem pra qualquer pipeline deste repositório

- Nunca inventar característica de produto que o usuário não confirmou por escrito (ver
  `persona/persona.md` — mesma regra vale aqui).
- Sempre entregar o vídeo final em H.264/AAC (compatibilidade universal).
- Sempre confirmar com o usuário duração, plataforma e qualquer dado do produto antes de
  gerar o arquivo final.
