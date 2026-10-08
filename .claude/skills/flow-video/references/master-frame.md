# FRAME_MESTRE (MODEL_001 + produto numa única imagem)

O Google Flow recebe **somente uma imagem de partida**: o FRAME_MESTRE (`products/PRODUCT_ID/master_frame.png`).
Nunca peça ao usuário para anexar separadamente `MODEL_001/reference.png` ou a imagem original do produto
no Flow. Nas cenas 2 e 3 entra também o último frame da cena anterior (continuidade).

## Entradas
- `assets/model/MODEL_001/reference.png` (identidade da pessoa; nunca apagar, nunca alterar)
- `model_identity.md` (roupa-base, microfone Hollyland, regras)
- a imagem original do produto (temporária) e `product.json` já analisado

## Composição
- Vertical 9:16 (idealmente 1080×1920), enquadramento da cintura para cima ou o que o produto pedir.
- A MODEL_001 segura, veste, usa ou apresenta o produto de forma natural e adequada ao tipo de produto.
- Rosto, cabelo, aparência, roupa-base e microfone de lapela Hollyland iguais à `reference.png`.
  Produto vestível: o produto substitui a roupa-base; o microfone continua preso no decote/gola.
- Produto fiel à imagem original: cores (qual item tem qual cor), quantidade, formato, textura,
  estampa, acabamento, proporções, acessórios e embalagem. Sem logos ou marcas inventados.
- O produto nunca altera o rosto/identidade da modelo; a modelo nunca altera a aparência do produto.
- Ambiente real e comercial, escolhido pelo contexto de uso (`product-analysis.md`). Sem objetos
  desnecessários, produtos concorrentes ou unidades extras do produto.
- Sem texto, ícones, selos, setas ou molduras. Infográfico: não leve nada disso para o frame.

## Gerar
1. Referência do produto: se a imagem original for um infográfico ou tiver fundo/texto, recorte só a
   região do produto num arquivo **temporário** (scratchpad; PIL), sem alterar o original.
2. Ferramenta: use a ferramenta de imagem conectada que aceite **várias referências** (o produto
   precisa de 2 imagens: modelo + produto). Hoje:
   - **ElevenLabs `creative_*`**: `creative_create_flow` → para cada referência
     `creative_create_asset_upload` (nome, mime, tamanho exato), `curl -X PUT -H "Content-Type: <mime>"
     --data-binary @arquivo "<upload_url>"`, `creative_finalize_asset_upload` (com `flow_id`) →
     `creative_generate_image` com `connect_from=[nó da modelo, nó do produto]`, modelo
     `gemini-3-pro-image` (compõe várias imagens e mantém personagem) ou `gpt-image-2`, 9:16,
     `generations_count` 1 ou 2 → `creative_get_flow_run_status` até concluir → baixe o resultado
     para `products/PRODUCT_ID/master_frame.png`. Nunca repita a chamada para "tentar de novo"
     sem decidir: cada chamada cobra de novo.
   - **Higgsfield `generate_image`** (referências por `media_id`) se estiver conectado e o upload for possível.
   Antes de gerar, informe a ferramenta, o modelo e o custo estimado (`estimate_only` quando existir).
   Máximo de **3 gerações** por produto; depois pare e pergunte ao usuário.
3. Prompt do frame (modelo para a ferramenta; preencha a partir do `product.json`):
```
Fotografia comercial vertical 9:16. A mulher da imagem de referência 1 (mesma pessoa: mesmo rosto,
cabelo, tom de pele, idade aparente e proporções; microfone de lapela Hollyland preto na gola)
{segura | veste | usa | apresenta} o produto da imagem de referência 2, {ação natural}. Produto
exatamente como na referência: {quantidade, cores, formato, textura, estampa, acabamento}.
Roupa: {roupa-base da model_identity.md | o próprio produto}. Ambiente: {ambiente}, real e
comercial, sem objetos extras. Luz natural suave. Sem texto, logos, selos ou ícones.
```
4. **Sem ferramenta de imagem disponível** (`MASTER_FRAME_TOOL_UNAVAILABLE`): não invente o frame nem
   declare READY. Entregue o prompt acima e diga que o usuário precisa gerar o `master_frame.png`
   numa ferramenta com duas referências (esta é a única etapa em que duas imagens entram numa ferramenta,
   nunca no Flow dos vídeos) e salvá-lo no caminho; então siga ao validar.

## Validar o frame (obrigatório)
Veja a imagem (leitura de imagem) e compare com `reference.png` e a imagem do produto:
[ ] mesma pessoa (rosto, cabelo) · [ ] roupa correta · [ ] microfone presente · [ ] produto correto
[ ] quantidade · [ ] cores (e qual item tem qual cor) · [ ] formato · [ ] textura · [ ] estampa
[ ] acabamento · [ ] sem texto/ícones/logos inventados · [ ] ambiente adequado · [ ] 9:16 · [ ] sem objetos extras
Se algo falhar: **não declare READY**; marque `MASTER_FRAME_NOT_APPROVED`, diga exatamente o que está
errado e corrija o frame (ajustando o prompt, dentro do limite de 3 gerações). Mostre o frame ao
usuário (`SendUserFile` quando disponível). O usuário tem a última palavra visual.
Registre em `product.json`: `master_frame_sha256` e `master_frame_aprovado`.

## Imagem original é temporária
Depois que (1) o produto foi analisado, (2) o FRAME_MESTRE foi criado e aprovado, (3) os dados foram
gravados em `product.json` e (4) os 3 prompts foram criados:
- grave só metadados textuais: `product_id`, nome, resumo das características, `imagem_original_sha256`,
  nome do arquivo original, `processado_em`, `imagem_original_removida: true`;
- remova a original do projeto: `git rm -f <arquivo>` (em `products/_inbox/` ou `references/`), apague
  recortes temporários e a pasta `references/` se ficar vazia;
- **preserve** `assets/model/MODEL_001/{reference.png,model_identity.md,approved.json}`,
  `master_frame.png`, `product.json`, `visual_bible.md`, `script.md` e os 3 `prompt.txt`.
Antes de remover, confirme: `master_frame.png` existe e foi aprovado, os 3 prompts existem e o
`product.json` tem os metadados. Se algo faltar, **não remova**.
Limite real: se a original já foi enviada ao GitHub (upload em `_inbox`), ela continua no histórico
do Git depois do commit de remoção; só sai da árvore de arquivos. Apagá-la do histórico exige
reescrever o histórico (não faça sem pedido explícito). O commit/push da limpeza segue a regra do
projeto: só com autorização do usuário.
