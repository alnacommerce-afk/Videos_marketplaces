---
description: Novo produto para vídeo no Google Flow: pede o upload da imagem, cria o FRAME_MESTRE e entrega os 3 prompts
argument-hint: [nome do produto]
---
Use a skill `flow-video`, seção "Novo produto: upload, análise e FRAME_MESTRE". Produto: $ARGUMENTS

Valide a MODEL_001 (único bloqueio). Se não houver imagem do produto, PARE e mostre o bloco "ENVIE A IMAGEM DO PRODUTO" com o link exato de upload; não crie roteiro, prompts nem frame. Ao receber ENVIEI: analise a imagem, crie e valide o FRAME_MESTRE (`master_frame.png`), crie `product.json`, `visual_bible.md`, `script.md` e os 3 prompts, remova a imagem original do Git e entregue na ordem: FRAME_MESTRE, CENA 1, CENA 2, CENA 3, checklist e `READY_TO_GENERATE`. O Flow recebe só o FRAME_MESTRE (mais o último frame nas cenas 2 e 3). Se o frame não representar bem a modelo ou o produto, não declare READY.
