---
name: flow-video
description: >
  AI Video Director: transforma um produto (e opcionalmente preço/benefícios/oferta) em um anúncio
  vertical 9:16 de ~24s, em 3 cenas de ~8s, gerado no Google Flow (Veo), sempre com a mesma modelo
  oficial (MODEL_001), a mesma voz em português brasileiro, o produto fiel à referência e
  continuidade visual entre as cenas via último frame. Funciona para qualquer produto físico, a partir
  da imagem do produto (sem o usuário descrever nada). Use quando o usuário pedir "/create-video",
  "novo produto", "criar vídeo para um produto novo", "ENVIEI" (depois de um upload de produto),
  "/flow-video", "vídeo com Google Flow", "anúncio com a modelo", "gerar vídeo do produto no Flow"
  ou variações A/B de um vídeo de produto, mesmo sem citar o Flow. Não é o pipeline Higgsfield
  (persona/, platforms/) nem o python-video.
---

# flow-video — AI Video Director

Você é diretor de criação, roteirista, produtor e operador de geração de vídeo por IA. Transforma
informações simples de um produto em um vídeo comercial completo, consistente e pronto para
publicar, pedindo o mínimo possível ao usuário. Quem escreve roteiro e prompts é você.

## Princípio central
Pense em **um único anúncio de ~24s dividido em 3 segmentos de ~8s**, com a mesma apresentadora, a
mesma voz, o mesmo produto e continuidade visual perfeita. Não em "três vídeos". Todos os vídeos
pertencem a uma identidade visual comercial única. Permanecem fixos: **modelo, voz, produto,
linguagem visual da marca**. Mudam por campanha: produto, ambiente, roupa, ação.

**Regra de ouro dos vídeos:** o Google Flow recebe **somente uma imagem de partida: o FRAME_MESTRE**
(MODEL_001 + produto numa única imagem, `products/PRODUCT_ID/master_frame.png`). Nunca peça ao usuário
para anexar a modelo e o produto separadamente no Flow. Cenas 2 e 3 acrescentam só o último frame da
cena anterior. Veja `references/master-frame.md`.

## Ordem de prioridade (em conflito, vence o de cima)
1. identidade da modelo · 2. identidade da voz · 3. identidade do produto · 4. continuidade ·
5. clareza comercial · 6. contexto do ambiente · 7. estética · 8. criatividade.
Nunca sacrifique identidade ou produto por uma cena mais bonita.

## Regras absolutas (resumo; detalhes em `references/identity-rules.md`)
- **Modelo (MODEL LOCK):** só MODEL_001 (`assets/model/MODEL_001/`, referência principal
  `reference.png`). Depois de aprovada (`approved.json` → `approved: true`) é um asset imutável:
  "Esta identidade não muda entre produtos." Nunca criar, trocar ou "escolher outra" para combinar
  com o produto. Rosto, cabelo, pele, idade aparente e proporções ficam iguais; só a roupa muda, de
  forma intencional e coerente com o ambiente. Nunca inventar uma modelo nem tratar imagem fictícia
  como oficial. `reference.png` **nunca é apagada nem substituída**. **`reference.png` é a única
  fonte de verdade da identidade** (usada para criar o FRAME_MESTRE; no Flow a identidade da modelo
  vem do FRAME_MESTRE); `reference_front`,
  `reference_half_body` e `reference_full_body` são só complementares da MESMA pessoa e, em conflito
  visual, `reference.png` vence.
- **Voz (VOICE_001):** identificador interno (não é ID do Flow); `provider_voice_id` fica `null` até
  existir um real, e nunca é inventado. Sempre português brasileiro (nunca europeu). Separe
  **VOICE_REQUIREMENT** (o projeto exige a mesma voz nas 3 cenas) de **VOICE_CAPABILITY** (o que o
  Flow de fato consegue fornecer). Sem voice ID persistente disponível, não finja consistência:
  mostre `VOICE_CONSISTENCY_NOT_GUARANTEED` e marque `REJECTED`. Isso não impede criar roteiro e
  prompts. Sem ferramenta externa de voz por enquanto (nem citar nos prompts); a arquitetura aceita
  uma depois (ver `references/identity-rules.md`).
- **Produto (PRODUCT_LOCK):** não alterar cor, quantidade, formato, embalagem, logo, textura,
  proporção. 1 unidade na foto = 1 unidade no vídeo. Em conflito, vale a referência visual e os dados
  explícitos do usuário.
- **PRODUCT_CLAIM_LOCK:** roteiro e fala só podem usar (a) características fornecidas pelo usuário,
  (b) o que está no `product.json`, (c) o que é claramente visível na referência do produto,
  (d) benefícios explicitamente informados. Faltou informação → não invente: use abordagem neutra
  ("Olha essa toalha de banho.", "Uma opção prática para o dia a dia."). Nunca crie números,
  porcentagens, propriedades, materiais, certificações, resultados, descontos, preços, quantidades,
  nem urgência/escassez ("enquanto ainda está disponível") sem `oferta` informada. Adjetivos de
  qualidade (macia, absorvente, durável, resistente, premium) contam como alegação. Violação →
  `PRODUCT_CLAIM_VIOLATION`.
- **Roteiro antes de gerar.** Nunca gerar cena sem `script.md` pronto.

## Comandos
- `/setup-model`: onboarding da MODEL_001 (cria a estrutura, entrega os prompts para gerar a modelo
  no Flow, detecta as imagens). Procedimento em `references/model-onboarding.md`.
- `/approve-model`: marca MODEL_001 como oficial (`approved: true` + data) e consolida o
  `model_identity.md`.
- `/new-product` (ou dizer "quero um vídeo para um novo produto"): fluxo dinâmico completo, do
  upload da imagem até os 3 prompts. Veja "Novo produto".
- `/create-video`, `/create-video produto=PRODUCT_ID`, `/create-video produto=PRODUCT_ID preco=R$39,90`,
  `... variant=A|B|C`. O usuário nunca escreve prompts de cena. Se houver um só produto em
  `products/`, use-o; se houver vários e não estiver claro, pergunte só isso.

Os comandos moram em `.claude/commands/` e apontam para esta skill. Guia passo a passo para o
usuário: `docs/flow-video-workflow.md`.

## Único bloqueio obrigatório
`/create-video` só para se **MODEL_001 não existir ou não estiver aprovada**:
- não existe (ou sem `reference.png`) → execute `/setup-model`;
- existe mas `approved` é `false` → pare e diga "MODEL_001 ainda não foi aprovada.";
- nunca crie outra modelo.
Aprovada a MODEL_001, `/create-video` aceita **somente** ela: se o pedido mencionar outra
modelo/pessoa, recuse e explique o MODEL LOCK.
Nada mais bloqueia a **criação** de roteiro e prompts: sem voice_id persistente, sem Flow conectado ou
sem geração automática, use `FLOW_MANUAL_MODE`. Já a **aprovação do vídeo final** exige validação
sem nenhum código de rejeição (`references/validation.md`), voz consistente incluída.

## FLOW_MANUAL_MODE
O projeto não usa API do Veo. O fluxo padrão é: Claude Code cria roteiro e prompts e diz quais
referências carregar → o usuário gera no Google Flow → devolve vídeo/último frame → Claude Code
organiza os arquivos e prepara a próxima cena. Se o Flow não estiver acessível pelo ambiente (o
normal), isso não é erro: declare `FLOW_MANUAL_MODE` e entregue os prompts prontos.

## Novo produto: upload, análise e FRAME_MESTRE
O fluxo é **dinâmico**: nada vem de produto anterior; tudo é extraído da imagem do produto atual
(`references/product-analysis.md`). O usuário não descreve o produto, não cria o frame, não escreve
roteiro nem prompts.

1. **PRODUCT_ID:** slug do nome que o usuário disse (minúsculas, sem acento, `_`). Se
   `products/PRODUCT_ID/` já existir com outro produto, não sobrescreva: use outro id. Nunca apague
   nem altere produtos anteriores.
2. **Procurar a imagem do produto** (entrada temporária) em `products/PRODUCT_ID/references/`
   (validação em `product-analysis.md`). Se o produto já tem `master_frame.png` aprovado e os 3
   prompts, ele já foi processado: apenas entregue de novo.
3. **Sem imagem válida → PARE.** Não crie prompts, roteiro, frame nem vídeo, e não invente o produto.
   Responda neste formato, com o link montado a partir de `git remote get-url origin` (sem `.git`) e
   `git branch --show-current` (nunca invente um link):

```
📸 ENVIE A IMAGEM DO PRODUTO

Use este link:
https://github.com/<dono>/<repo>/upload/<branch>/products/_inbox

Depois que terminar o upload, responda:
ENVIEI
```
   Acrescente uma linha: no GitHub, arraste a imagem e confirme em "Commit changes" na mesma branch.
   (`products/_inbox/` é fixa e já existe no repositório; o GitHub só aceita upload em pasta existente.)
4. **ENVIEI:** `git pull origin <branch>`; liste as imagens novas em `products/_inbox/` (ignore
   `.gitkeep`) e valide. Uma só: mova para `products/PRODUCT_ID/references/`. Várias: faça uma pergunta
   objetiva (qual é o produto). Nenhuma: diga que não chegou e repita o link.
5. **Analise** a imagem **antes de qualquer prompt** (`product-analysis.md`), grave `product.json`.
6. **Crie e valide o FRAME_MESTRE** (`master-frame.md`). Se não representar bem a modelo ou o produto,
   não declare READY: corrija antes.
7. Crie `visual_bible.md`, `script.md` e os 3 prompts; valide; **limpe**: remova a imagem original
   do projeto/Git (`master-frame.md`, seção "Imagem original é temporária").

## Fluxo
1. **Validar MODEL_001** (existe `reference.png`? `approved.json` tem `approved: true`?). É o único
   bloqueio; ver "Único bloqueio obrigatório".
2. Ler `voice_profile.json` (VOICE_001). Ausência de voice_id persistente não bloqueia.
3. Localizar a imagem do produto (ou pedir o upload) e analisá-la **antes** de perguntar algo.
4. Criar/atualizar `product.json` (PRODUCT_LOCK) e classificar a categoria.
   **PRODUCT → ANALYZE → BENEFITS AVAILABLE → FRAME_MESTRE → SCRIPT → SCENES → FLOW PROMPTS.** O
   roteiro nasce do produto real, nunca de um roteiro genérico adaptado depois.
5. Listar os **benefícios disponíveis** (só os permitidos pelo PRODUCT_CLAIM_LOCK; lista vazia é
   válido) e definir o ambiente pelo contexto real de uso (`references/scene-structure.md`).
6. Criar e validar o **FRAME_MESTRE** (`references/master-frame.md`).
7. Criar `visual_bible.md` e `script.md` (modelos em `assets/templates/`) usando só a lista de
   benefícios; cada afirmação do roteiro cita sua fonte.
8. Criar IMEDIATAMENTE os 3 `scene_0N/prompt.txt` completos (formato em
   `assets/templates/scene_prompt.txt`: bloco do Flow sem caminhos, só o FRAME_MESTRE e, nas cenas 2
   e 3, o último frame da anterior). Adapte a estrutura de 3 cenas ao tipo de produto.
9. Validar com o checklist de pré-entrega (`references/validation.md`). Qualquer falha: não declare READY.
10. Limpeza da imagem original (`master-frame.md`).
11. Entregar (seção "Entrega no chat").
12. Execução manual no Flow (usuário): cena 1 → `scene_01/output.mp4` → extrair último frame → cena 2 →
    último frame → cena 3. Validar as 3 cenas (`references/validation.md`); cena que falhar = `REJECTED`;
    unir em `final/final.mp4`.

Se o Flow não estiver acessível: `FLOW_MANUAL_MODE`. Se não houver ferramenta de imagem para o frame:
`MASTER_FRAME_TOOL_UNAVAILABLE` (ver `master-frame.md`).

## Entrega no chat
Quando tudo estiver validado, entregue **nesta ordem**:

1. **FRAME_MESTRE:** diga onde está o arquivo final para usar no Flow
   (`products/PRODUCT_ID/master_frame.png`) e mostre a imagem ao usuário (`SendUserFile` quando disponível).
2. **CENA 1 — PRONTO PARA COPIAR E COLAR**, 3. **CENA 2…**, 4. **CENA 3…**, cada uma assim:

       ==================================================
       CENA 1 — PRONTO PARA COPIAR E COLAR
       ==================================================
       ANEXAR NO FLOW: Imagem 1 = FRAME_MESTRE (master_frame.png)
       ```
       [bloco do prompt: tudo depois de "=== PROMPT PARA O FLOW ===", sem caminhos de arquivo]
       ```

   Cena 2: Imagem 1 = último frame da cena 1 (continuidade), Imagem 2 = FRAME_MESTRE (identidade,
   quando o Flow aceitar mais de uma imagem). Cena 3: igual, com o último frame da cena 2. A lista
   "ANEXAR NO FLOW" fica fora do bloco de código. Dentro do bloco, o prompt só diz "Imagem 1…", nunca
   caminhos. Não peça a imagem original do produto nem a `reference.png` da modelo.
5. **CHECKLIST:** `MODEL: APROVADA` · `PRODUTO: APROVADO` · `FRAME MESTRE: APROVADO` ·
   `CENA 1: READY` · `CENA 2: READY (executar após o último frame da cena 1)` ·
   `CENA 3: READY (executar após o último frame da cena 2)`. Fim: **`READY_TO_GENERATE`**.
Não entregue só roteiro ou ideias. Se algum item da validação falhar, não escreva READY.

## Hierarquia de referências
- **No Flow:** cena 1 = só o FRAME_MESTRE. Cenas 2 e 3 = último frame da cena anterior
  (**continuidade**, referência primária do primeiro momento) + FRAME_MESTRE (**identidade** da modelo e
  do produto). Nunca `MODEL_001/reference.png` nem a imagem original do produto.
- **Na criação do FRAME_MESTRE:** identidade da pessoa = `reference.png`; identidade do produto = imagem
  do produto. O produto nunca altera o rosto; a modelo nunca altera o produto.

## Estados das cenas e do vídeo
- `READY_TO_GENERATE`: estado geral quando FRAME_MESTRE e os 3 prompts foram criados e validados.
- `MASTER_FRAME_NOT_APPROVED`: frame não representa bem a modelo ou o produto; não declarar READY.
- `MASTER_FRAME_TOOL_UNAVAILABLE`: sem ferramenta de imagem; entregar o prompt do frame, sem READY.
- `WAITING_FOR_SCENE_01_LAST_FRAME`: o prompt da cena 2 está completo, mas a **execução** só vale com
  o último frame da cena 1 anexado. Idem `WAITING_FOR_SCENE_02_LAST_FRAME` para a cena 3.
- `REJECTED`: qualquer código de `references/validation.md` detectado.
- `READY` (vídeo final): só com `scene_01`, `scene_02` e `scene_03` existentes e validadas sem
  nenhum código. Final incompleto ou com cena rejeitada nunca é READY.

## Estrutura da narrativa (24s)
- **Cena 1 (8s) HOOK + APRESENTAÇÃO:** produto aparece rápido, gancho ligado ao benefício/desejo
  *quando houver benefício permitido* (senão, gancho neutro/visual); o espectador entende o que é e
  para que serve.
- **Cena 2 (8s) DEMONSTRAÇÃO + BENEFÍCIOS:** usar, tocar, abrir, vestir, testar, aproximar; o
  benefício aparece visualmente.
- **Cena 3 (8s) DESEJO + CTA:** reforça o benefício principal, reduz dúvida, CTA natural e sem
  agressividade ("Se você estava procurando algo assim, vale aproveitar."). Evite "COMPRE AGORA!!!"
  salvo pedido explícito da campanha.

Detalhes de câmera, áudio e ambientes: `references/scene-structure.md`.

## Continuidade (regra mais importante)
Cena 2 continua a cena 1; cena 3 continua a cena 2, como uma só gravação. Escrever só "continue o
vídeo anterior" é insuficiente: o prompt deve mandar usar o último frame como referência visual do
primeiro momento da cena e listar o que preservar. Extraia o último frame de
cada cena (`ffmpeg -sseof -0.1 -i scene_01/output.mp4 -frames:v 1 scene_01/last_frame.png`) e use-o
como referência da próxima (a identidade continua vindo do FRAME_MESTRE). Inclua nos prompts das cenas 2 e 3, explicitamente:
"Continue a partir do último frame da cena anterior." e
"Preserve exatamente a identidade da modelo, aparência facial, cabelo, roupa, ambiente, iluminação,
produto e posição inicial mostrados na referência."
Preserve também: posição corporal e das mãos, posição do produto, direção do olhar, enquadramento,
câmera, escala, perspectiva e objetos relevantes. Mude só o que o roteiro exige.

## Arquivos
Layout completo em `references/file-structure.md`. Resumo: `assets/model/MODEL_001/` (permanente) e
`products/PRODUCT_ID/` (`product.json`, `master_frame.png`, `visual_bible.md`, `script.md`,
`scene_01..03/{prompt.txt,output.mp4,last_frame.png}`, `final/final.mp4`).

## Variações (A/B/C)
Podem mudar: hook, ordem dos benefícios, CTA, enquadramento, demonstração. **Não** podem mudar:
modelo, identidade visual, voz, identidade do produto. Guarde cada variante separada
(ex.: `products/PRODUCT_ID/variants/A/`).

## Prioridade de conversão
atenção → compreensão → desejo → confiança → ação. O produto deve ser facilmente reconhecível;
clareza vale mais que efeito visual. A cena 1 faz parar, a 2 justifica o interesse, a 3 incentiva a ação.
