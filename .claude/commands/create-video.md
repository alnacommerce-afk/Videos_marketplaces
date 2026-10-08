---
description: Cria roteiro e prompts das 3 cenas (~24s) de um produto com a MODEL_001, para o Google Flow
argument-hint: produto=PRODUCT_ID [preco=R$39,90] [variant=A|B|C]
---
Use a skill `flow-video`. Argumentos: $ARGUMENTS

Primeiro valide MODEL_001 (existe e `approved: true`); se não, pare e oriente `/setup-model` ou `/approve-model`. Esse é o único bloqueio. Depois siga o fluxo da skill e entregue `script.md`, `visual_bible.md` e os `prompt.txt` das 3 cenas. Se o Flow não estiver acessível, use `FLOW_MANUAL_MODE`.

Regras extras: o roteiro nasce do produto real (PRODUCT → ANALYZE → BENEFITS AVAILABLE → SCRIPT → SCENES → FLOW PROMPTS) e só usa o que o PRODUCT_CLAIM_LOCK permite; cenas 2 e 3 sem o último frame da anterior ficam `WAITING_FOR_SCENE_0N_LAST_FRAME`; referências em ordem: `MODEL_001/reference.png`, último frame, produto.

Se o produto ainda não foi processado (sem `master_frame.png`), siga "Novo produto" da skill (link de upload, ENVIEI, análise, FRAME_MESTRE). Entregue na ordem de "Entrega no chat". O Flow recebe só o FRAME_MESTRE (mais o último frame nas cenas 2 e 3).
