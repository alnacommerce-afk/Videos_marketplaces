# Guia rápido: flow-video

Vídeo de ~24s (3 cenas de ~8s, 9:16) com a mesma modelo, a mesma voz e o mesmo produto, gerado
**manualmente no Google Flow** (`FLOW_MANUAL_MODE`). O Claude Code escreve roteiro e prompts e
organiza os arquivos; você executa no Flow.

## Uma vez só: criar a modelo
1. **`/setup-model`**: o Claude entrega o prompt principal (e os opcionais) para criar a MODEL_001.
2. **Gerar a modelo no Flow** com esse prompt. Escolha a imagem que será a oficial.
3. **Salvar em `assets/model/MODEL_001/`** uma única imagem: `reference.png` (obrigatória e fonte de
   verdade da identidade). Complementares (`reference_front.png`, `reference_half_body.png`,
   `reference_full_body.png`) só se forem necessárias, sempre geradas a partir do `reference.png`
   para serem a mesma pessoa; em conflito, o `reference.png` vence.
4. **`/approve-model`**: `approved.json` vira `true` com a data. A partir daí a modelo é fixa.

## Para cada produto
5. **Adicionar o produto** em `products/PRODUCT_ID/`: fotos em `references/` e, se quiser, um
   `product.json` (nome, cor, quantidade, benefícios, preço). Ex.: `products/toalha_bege/`.
6. **`/create-video produto=toalha_bege`**: o Claude valida a MODEL_001, cria `script.md`,
   `visual_bible.md` e `scene_01..03/prompt.txt`. Você não escreve prompts.
   Regra: o roteiro só usa o que está no `product.json`, o que você informou ou o que é visível
   na foto (PRODUCT_CLAIM_LOCK). Sem benefícios informados, a fala é neutra. Quer destacar
   absorção, maciez, material? Informe, senão ela não aparece.
7. **Gerar a Cena 1 no Flow** (checklist: `docs/flow-generation-checklist.md`): carregue as referências listadas no topo de `scene_01/prompt.txt`
   (MODEL_001 + produto), cole o trecho "PROMPT PARA O FLOW". Salve em `scene_01/output.mp4`.
8. **Salvar o último frame** como `scene_01/last_frame.png` (o Claude extrai com ffmpeg se você
   mandar o vídeo, ou use "salvar frame" no Flow).
9. **Gerar a Cena 2** (sem `scene_01/last_frame.png` ela fica em `WAITING_FOR_SCENE_01_LAST_FRAME`):
   carregue MODEL_001 `reference.png` + `scene_01/last_frame.png` + produto. Salve
   `scene_02/output.mp4`.
10. **Salvar o último frame** da Cena 2 em `scene_02/last_frame.png`.
11. **Gerar a Cena 3**: MODEL_001 + produto + `scene_02/last_frame.png`. Salve `scene_03/output.mp4`.
12. **Unir os vídeos**: peça ao Claude para juntar as 3 cenas em `final/final.mp4`
    (`ffmpeg` concat) e validar modelo, voz, produto e continuidade.

## Se algo falhar
- "MODEL_001 ainda não foi aprovada": rode `/approve-model` (ou `/setup-model` se não há imagem).
- Voz diferente entre cenas (`VOICE_MISMATCH` / `VOICE_CONSISTENCY_NOT_GUARANTEED`): a cena é
  `REJECTED` e o vídeo final não é aprovado. Voz diferente nunca é aceita. O Flow pode não manter
  voz persistente; a solução definitiva (voz persistente) será adicionada depois sem refazer a skill.
- Cena `REJECTED` (`MODEL_MISMATCH`, `PRODUCT_MISMATCH`, `ENVIRONMENT_MISMATCH`,
  `CONTINUITY_BROKEN`, `WRONG_LANGUAGE`, `WRONG_ASPECT_RATIO`): regenerar a cena.
