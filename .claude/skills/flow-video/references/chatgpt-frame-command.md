# Fluxo padrão: o usuário cria o FRAME_MESTRE no ChatGPT e me envia

Decisão do usuário (2026-10-08): o FRAME_MESTRE (modelo + produto + ambiente) é criado **pelo usuário no ChatGPT
gratuito**, com um comando padrão, e enviado ao Claude. A skill **parte do frame pronto**: não gera frame (a ElevenLabs é só
plano B, com custo avisado) e não precisa receber a foto do produto (opcional).

## O que o usuário faz
1. No ChatGPT, anexa a foto da modelo (`reference.png` da MODEL_001) e a foto do produto e cola o **comando padrão**.
2. Confere a imagem (mesma modelo, quantidade certa do produto, ambiente coerente) e a envia pelo link de upload
   (`products/_inbox/`) ou anexa no chat.
3. Escreve **o que pode ser dito do produto** (nome, quantidade do kit, medidas, material, outros dados reais). Não
   precisa descrever o que já aparece na imagem.

## Comando padrão (ChatGPT)
```
Crie uma imagem dessa modelo utilizando esse produto, em um ambiente que condiz com o uso do produto.
Imagem 1 = a modelo: mantenha exatamente a mesma pessoa (rosto, cabelo, tom de pele, proporções), a mesma roupa
(camisa branca de manga longa com as mangas dobradas e calça preta) e o microfone de lapela preto na gola.
Imagem 2 = o produto: mantenha o produto exatamente como na foto (cor, formato, textura, estampa, acabamento).
Produto: {NOME DO PRODUTO}. Quantidade: exatamente {N} unidades idênticas, juntas, nas mãos da modelo, bem
visíveis e contáveis, sem separar nenhuma.
Formato vertical 9:16, plano médio (da cintura para cima), a modelo olhando para a câmera com um sorriso simpático,
as duas mãos visíveis segurando o produto à frente do corpo.
Ambiente: {AMBIENTE QUE COMBINA COM O USO}, claro, arrumado e realista, com cores que destaquem o produto, sem objetos
extras nem outros produtos. Luz natural suave. Sem texto, ícones, selos ou logotipos.
```
Se o ChatGPT gerar 2:3 (1024×1536), a modelo deve ficar centralizada: eu corto para 9:16 sem esticar.
Se ele recusar editar a foto da pessoa, gerar a imagem errada ou o limite gratuito acabar: plano B = ElevenLabs.

## O que o Claude faz com o frame (passo a passo)
1. Receber o frame (`_inbox/` ou anexo), validar o arquivo e **cortar para 9:16** se for 2:3 (nunca esticar).
2. **Validar o frame** (checklist de `master-frame.md`): mesma modelo e roupa, microfone presente, **quantidade exata**,
   produto coerente com o que o usuário disse (e com a foto, se enviada), ambiente adequado, sem texto/logos. Sem a foto do
   produto, só verifico quantidade e coerência, não a fidelidade fina. Diga isso.
3. Salvar `master_frame.png` e criar `product.json` a partir do **texto do usuário + o que o frame mostra** (PRODUCT_CLAIM_LOCK).
   Perguntar só o que for crítico e ambíguo (ex.: qual kit).
4. Escrever `script.md`, `visual_bible.md` e os 3 prompts com as lições aprendidas: modo Frames (quadro inicial), aparência
   descrita sem traços do rosto, ação por faixa de tempo + "Não faz", "sempre exatamente N", câmera fixa sem close/fusões,
   quadro de continuidade em ~7,5 s.
5. Entregar o FRAME_MESTRE e os 3 prompts no chat.

## Lições
- **Use o comando padrão completo.** Com uma frase curta ("crie uma imagem dessa modelo usando esse produto num ambiente que condiz
  com o uso"), o ChatGPT fez uma cena de uso (modelo mexendo uma panela) com **1 colher** em vez do kit de 5, avental novo e
  um cenário cheio de objetos (legumes, tábuas, pote com outras colheres ao fundo). O vídeo é fiel ao frame, então o que está no
  frame é o que o vídeo mostra. Para kits, peça "exatamente N unidades juntas nas mãos"; para cena de uso, aceite 1 unidade e
  diga a quantidade só na fala (dado do usuário).
- **2:3 → 9:16:** corte só o lado com menos informação (aqui, 160 px da esquerda, que era só o braço). Confira que rosto, produto e
  mãos continuam inteiros.
- **Cena de uso:** escreva a ação por faixa de tempo com um movimento curto e constante (mexer devagar) e "Não faz" (não troca de
  colher, não pega as do pote, cenário parado).
