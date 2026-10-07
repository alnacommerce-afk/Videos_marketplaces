---
name: flow-video
description: >
  AI Video Director: transforma um produto (e opcionalmente preço/benefícios/oferta) em um anúncio
  vertical 9:16 de ~24s, em 3 cenas de ~8s, gerado no Google Flow (Veo), sempre com a mesma modelo
  oficial (MODEL_001), a mesma voz em português brasileiro, o produto fiel à referência e
  continuidade visual entre as cenas via último frame. Use quando o usuário pedir "/create-video",
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
  como oficial. **`reference.png` é a única fonte de verdade da identidade**; `reference_front`,
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

## Fluxo
1. **Validar MODEL_001** (existe `reference.png`? `approved.json` tem `approved: true`?). É o único
   bloqueio; ver "Único bloqueio obrigatório".
2. Ler `voice_profile.json` (VOICE_001). Ausência de voice_id persistente não bloqueia.
3. Localizar referências do produto; analisar imagens, nome e descrição **antes** de perguntar algo.
4. Criar/atualizar `product.json` (PRODUCT_LOCK) e classificar a categoria.
   **PRODUCT → ANALYZE → BENEFITS AVAILABLE → SCRIPT → SCENES → FLOW PROMPTS.** O roteiro nasce do
   produto real, nunca de um roteiro genérico adaptado depois.
5. Listar os **benefícios disponíveis** (só os permitidos pelo PRODUCT_CLAIM_LOCK; lista vazia é
   válido) e definir o ambiente pelo contexto real de uso (`references/scene-structure.md`).
6. Criar `visual_bible.md` e `script.md` (modelos em `assets/templates/`) usando só essa lista; cada
   afirmação do roteiro cita sua fonte.
7. Criar `scene_0N/prompt.txt` das 3 cenas no formato de `assets/templates/scene_prompt.txt`
   (seções, referências a carregar no Flow, continuidade explícita). A cena 2 e a 3 dependem do
   último frame da anterior: sem ele a cena **não está pronta** (ver "Estados das cenas").
8. Cena 1 no Flow (usuário) → vídeo salvo em `scene_01/output.mp4` → extrair último frame.
9. Cena 2 com `scene_01/last_frame.png` como referência → extrair último frame.
10. Cena 3 com `scene_02/last_frame.png` como referência.
11. Validar as 3 cenas (`references/validation.md`); cena que falhar = `REJECTED`.
12. Unir as cenas em `final/final.mp4` e apresentar o resultado.

Se o Flow não estiver acessível: `FLOW_MANUAL_MODE` (seção acima). Entregue tudo até o passo 7 e
diga exatamente o que o usuário precisa fazer a seguir.

## Hierarquia de referências no Flow
1. `assets/model/MODEL_001/reference.png`: **identidade da modelo** (obrigatória em todas as cenas)
2. último frame da cena anterior: **continuidade da cena** (cenas 2 e 3)
3. referência visual do produto: **identidade do produto**
Em conflito, cada referência manda só no seu domínio. A referência do produto nunca altera a
identidade da modelo. Complementares da modelo (front/half_body/full_body) nunca substituem a
`reference.png`. Cena 2 = `reference.png` + `scene_01/last_frame.png` + produto; cena 3 =
`reference.png` + `scene_02/last_frame.png` + produto.

## Estados das cenas e do vídeo
- `WAITING_FOR_SCENE_01_LAST_FRAME`: cena 2 sem `scene_01/last_frame.png`; o prompt não é utilizável.
  Idem `WAITING_FOR_SCENE_02_LAST_FRAME` para a cena 3.
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
como referência da próxima (a identidade continua vindo de `reference.png`). Inclua nos prompts das cenas 2 e 3, explicitamente:
"Continue a partir do último frame da cena anterior." e
"Preserve exatamente a identidade da modelo, aparência facial, cabelo, roupa, ambiente, iluminação,
produto e posição inicial mostrados na referência."
Preserve também: posição corporal e das mãos, posição do produto, direção do olhar, enquadramento,
câmera, escala, perspectiva e objetos relevantes. Mude só o que o roteiro exige.

## Arquivos
Layout completo em `references/file-structure.md`. Resumo: `assets/model/MODEL_001/` (permanente) e
`products/PRODUCT_ID/` (`product.json`, `references/`, `visual_bible.md`, `script.md`,
`scene_01..03/{prompt.txt,output.mp4,last_frame.png}`, `final/final.mp4`).

## Variações (A/B/C)
Podem mudar: hook, ordem dos benefícios, CTA, enquadramento, demonstração. **Não** podem mudar:
modelo, identidade visual, voz, identidade do produto. Guarde cada variante separada
(ex.: `products/PRODUCT_ID/variants/A/`).

## Prioridade de conversão
atenção → compreensão → desejo → confiança → ação. O produto deve ser facilmente reconhecível;
clareza vale mais que efeito visual. A cena 1 faz parar, a 2 justifica o interesse, a 3 incentiva a ação.
