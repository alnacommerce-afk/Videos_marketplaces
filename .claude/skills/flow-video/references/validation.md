# Validação e rejeição

## Checklist antes de entregar (obrigatório; falha = não declarar READY)
- [ ] MODEL_001 correta e aprovada · [ ] identidade da modelo preservada (rosto, cabelo, roupa, microfone)
- [ ] produto correto · [ ] quantidade · [ ] cores · [ ] formato · [ ] textura · [ ] estampa
- [ ] FRAME_MESTRE criado e validado contra `reference.png` e a imagem do produto (`master-frame.md`)
- [ ] nenhum benefício, característica ou especificação inventados (PRODUCT_CLAIM_LOCK)
- [ ] ambiente adequado · [ ] 3 cenas criadas · [ ] continuidade planejada (último frame nas cenas 2 e 3)
- [ ] falas em português brasileiro · [ ] cada fala cabe em ~8 s (18 a 24 palavras) · [ ] formato 9:16
- [ ] prompts sem caminhos de arquivo e só com FRAME_MESTRE (+ último frame), sem pedir a original nem a `reference.png`
- [ ] nada reaproveitado de produto anterior · [ ] `product.json` com metadados (hash da original, data)
- [ ] imagem original do produto removida do projeto/Git (`master-frame.md`) · [ ] MODEL_001 preservada
Informação crítica ilegível ou ambígua: não invente, faça uma pergunta objetiva antes.

## Ao receber o vídeo de uma cena (usar `video-review.md`)
- [ ] primeiro quadro igual ao quadro inicial (mesma pessoa, roupa, cenário)
- [ ] quantidade do produto correta **em todos os quadros** (não só no primeiro)
- [ ] último quadro nítido (senão usar o quadro de ~7,5 s) · [ ] áudio presente · [ ] 9:16 · [ ] ~8 s
- [ ] fala em português brasileiro (verificada por transcrição ou pelo usuário, não presumida)

## Antes do /create-video (pré-checagem)
- `assets/model/MODEL_001/` existe e tem `reference.png`?
- `approved.json` tem `approved: true`?
Não existe → `/setup-model`. Existe sem aprovação → "MODEL_001 ainda não foi aprovada." Nunca
criar outra modelo. Voz sem voice_id persistente ou Flow desconectado **não** impedem criar roteiro e prompts (`FLOW_MANUAL_MODE`), mas a voz continua tendo que ser consistente para aprovar o vídeo final.

## Depois de gerar
Verifique cada item:
- MODELO: mesma pessoa nas três cenas
- VOZ: mesma voz nas 3 cenas (verificada, não presumida)
- PRODUTO: correto, cor, quantidade e características corretas
- AMBIENTE: coerente com o produto
- CONTINUIDADE: cena 2 continua a 1; cena 3 continua a 2
- FORMATO: vertical 9:16
- NARRATIVA: hook, apresentação, demonstração, benefícios, CTA
- IDIOMA: português brasileiro
- ALEGAÇÕES: toda frase da fala tem fonte (PRODUCT_CLAIM_LOCK)

## Rejeição automática
Cada problema abaixo, quando detectado, marca a cena `REJECTED`. Registre o código em
`products/PRODUCT_ID/validation.md` (cena, código, o que foi visto).

| Código | Quando |
|---|---|
| `MASTER_FRAME_NOT_APPROVED` | o FRAME_MESTRE não representa corretamente a modelo ou o produto (antes de qualquer cena) |
| `MODEL_MISMATCH` | pessoa diferente da MODEL_001 (rosto, cabelo, pele, idade, proporções) |
| `VOICE_MISMATCH` | voz diferente da apresentadora entre cenas |
| `PRODUCT_MISMATCH` | produto alterado: cor, quantidade, formato, embalagem, logo, textura |
| `ENVIRONMENT_MISMATCH` | ambiente incoerente com o uso do produto, ou diferente do da cena anterior sem o roteiro pedir |
| `CONTINUITY_BROKEN` | o início da cena não parte do último frame anterior (corpo, mãos, produto, olhar, enquadramento, luz, roupa) |
| `WRONG_LANGUAGE` | fala fora do português brasileiro (inclui português europeu) |
| `WRONG_ASPECT_RATIO` | fora de vertical 9:16 |
| `PRODUCT_CLAIM_VIOLATION` | roteiro ou fala com característica, benefício, número, resultado, material, preço, desconto ou urgência que não está em `product.json`, no que o usuário informou ou visível na referência |
| `VOICE_CONSISTENCY_NOT_GUARANTEED` | a voz não pôde ser mantida/verificada de forma consistente (vai junto com `VOICE_MISMATCH`, ou sozinha quando não há como verificar) |

- `VOICE_CONSISTENCY_NOT_GUARANTEED` também aparece sozinho quando o Flow não oferece voice ID
  persistente (capacidade) para cumprir a mesma voz (requisito): a cena fica `REJECTED` até o
  usuário verificar e confirmar a consistência. Não finja consistência.
- Antes de gerar os prompts, passe cada frase da fala pelo PRODUCT_CLAIM_LOCK; o que não tiver fonte sai.
- Voz diferente nunca é resultado aceitável, mesmo que a cena esteja boa.
- Estados: `WAITING_FOR_SCENE_01_LAST_FRAME` (cena 2 sem `scene_01/last_frame.png`) e
  `WAITING_FOR_SCENE_02_LAST_FRAME` (cena 3 sem `scene_02/last_frame.png`) significam cena não pronta.
  Vídeo final `READY` só com `scene_01`, `scene_02` e `scene_03` existentes e validadas sem código.
- O vídeo final só é considerado aprovado se as 3 cenas passarem sem nenhum código. Do contrário,
  `final.mp4` fica como rascunho reprovado e o Claude diz exatamente o que regenerar.
- Se for possível corrigir automaticamente (regenerar com prompt ajustado), corrija; se não,
  informe exatamente o problema. Nunca marque como concluído um vídeo com cena `REJECTED`.
