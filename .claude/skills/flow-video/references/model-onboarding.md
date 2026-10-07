# Onboarding da MODEL_001 (`/setup-model` e `/approve-model`)

A modelo oficial nunca é inventada pelo Claude: é gerada pelo usuário no Google Flow a partir dos
prompts abaixo e só vale depois de aprovada. Não crie imagem fictícia e não trate nada como oficial
antes de `/approve-model`.

## /setup-model
1. Verifique `assets/model/MODEL_001/`. Se faltar algum arquivo de configuração, crie-o a partir de
   `assets/templates/model/` (nunca sobrescreva um existente).
2. Veja quais imagens existem: `reference.png`, `reference_front.png`, `reference_half_body.png`,
   `reference_full_body.png`.
3. Estados:
   - **Sem `reference.png`** → entregue o PROMPT PRINCIPAL e explique: gerar **uma única** imagem no
     Flow, salvar como `reference.png` em `assets/model/MODEL_001/`, depois rodar `/setup-model` de
     novo. Mostre os prompts das complementares como **opcionais para depois**, só se forem
     necessárias. Não peça quatro modelos.
   - **Com `reference.png`, `approved: false`** → confirme as imagens detectadas, liste as que
     faltam (opcionais), peça ao usuário para conferir que todas são a mesma pessoa e, se estiver
     satisfeito, rodar `/approve-model`.
   - **`approved: true`** → informe que MODEL_001 já é oficial e está bloqueada; não gere novo
     prompt de modelo. Trocar a modelo exige decisão explícita do usuário e é fora desta skill.

## Prompt principal (reference.png), gere no Flow
O objetivo é uma **apresentadora comercial consistente**, não "uma mulher bonita": rosto com traços
marcantes e reconhecíveis (para o Flow conseguir repeti-los), aparência natural e confiável, boa
presença diante da câmera, versátil para qualquer categoria de produto. Copie e entregue assim
(ajuste só se o usuário pedir outra característica):

```
Fotografia realista de uma apresentadora comercial brasileira, mulher adulta de aproximadamente 30
anos, em pé, de frente para a câmera, corpo inteiro (da cabeça aos pés), enquadramento vertical 9:16,
câmera na altura dos olhos. Postura aberta e relaxada, olhando direto para a câmera com expressão
amigável, simpática e confiável, leve sorriso natural. Boa presença diante da câmera: parece uma
pessoa real, acessível, que inspira confiança para apresentar produtos.

IDENTIDADE FACIAL (traços fixos e reconhecíveis):
- Rosto oval com maçãs do rosto levemente marcadas e queixo suave.
- Olhos castanho-escuros, amendoados, expressivos, com cílios naturais.
- Sobrancelhas castanho-escuras, bem definidas, de arco suave.
- Nariz de ponte média e ponta delicada.
- Boca de lábios médios; ao sorrir surgem covinhas discretas nas bochechas e os dentes ficam
  parcialmente à mostra, sorriso aberto e sincero.
- Uma pequena pinta discreta na bochecha esquerda, perto do canto da boca (marca de reconhecimento).
- Pele morena clara a média, textura natural com poros visíveis, uniforme e saudável, sem retoque
  exagerado.

CABELO: castanho escuro com reflexos suaves, abaixo dos ombros, ondulado leve, repartido de lado,
penteado simples e prático, sem franja cobrindo o rosto.

CORPO: proporções naturais e equilibradas, estatura média, aparência saudável e comum.

ROUPA BASE NEUTRA: camiseta lisa off-white de caimento simples e calça reta de cor neutra, sem
estampas, sem logotipos. Sem joias, relógio ou acessórios chamativos, sem maquiagem pesada.

ESTILO: apresentadora comercial versátil, funciona tanto para produtos de cozinha, casa, banho,
roupas, beleza, praia, pet ou ferramentas; não pertence visualmente a nenhuma categoria específica.

TÉCNICO: iluminação uniforme e suave, sem sombras duras no rosto, fundo neutro liso cinza claro,
rosto totalmente visível e nítido, sem elementos que dificultem identificar o rosto.
```

## Referências complementares (só quando necessárias, a MESMA pessoa)
A primeira imagem criada e aprovada é a `reference.png`. As outras só são criadas depois, se algum
vídeo precisar de mais ângulos. Nunca gere quatro "modelos" tentando representar a mesma pessoa.
Estas imagens são **derivadas** da `reference.png` (sempre a MODEL_001 aprovada como referência; em conflito visual, `reference.png` vence): no Flow, anexe `reference.png` como imagem de
referência e use este bloco no começo de cada prompt. Nunca gere as referências de forma
independente, cada uma sairia com uma pessoa diferente.

```
Esta é a MESMA pessoa da imagem de referência. Preserve exatamente a identidade da pessoa
apresentada na referência: o mesmo rosto, olhos, sobrancelhas, nariz, boca, covinhas, a pinta na
bochecha esquerda, o mesmo cabelo (cor, comprimento, ondulação, repartição), tom de pele, idade
aparente, proporções corporais e a mesma roupa. Não criar outra pessoa, nem uma pessoa parecida.
```

Depois do bloco, acrescente o enquadramento:
- `reference_front.png`: "Close do rosto e ombros, de frente, olhar para a câmera, expressão
  neutra-simpática, iluminação uniforme, fundo neutro cinza claro, 9:16."
- `reference_half_body.png`: "Enquadramento da cintura para cima, de frente, postura natural,
  iluminação uniforme, fundo neutro cinza claro, 9:16."
- `reference_full_body.png`: "Corpo inteiro, da cabeça aos pés, de frente, postura natural,
  iluminação uniforme, fundo neutro cinza claro, 9:16."

Se o Flow devolver alguém diferente da referência, descarte a imagem; só vale a que for a mesma
pessoa. Se o usuário trocar traços do prompt principal (ex.: cor do cabelo), a pinta e os demais
traços marcantes devem continuar descritos para manter o reconhecimento.

## /approve-model
0. Estado inicial: `approved` permanece `false` até a execução desta etapa; nenhum outro comando
   o altera.
1. Exija `reference.png`: verifique no disco que o arquivo existe, não está vazio e é uma imagem
   (ex.: `ls -l` e `file`). Sem isso, **não aprove**, mantenha `approved: false` e mande rodar
   `/setup-model`.
2. Confirme com o usuário (se ele acabou de pedir `/approve-model` explicitamente, isso basta) que
   aquela é a modelo oficial.
3. Edite `approved.json`: `approved: true`, `approved_at` com a data de hoje (AAAA-MM-DD).
4. Se o usuário puder descrever (ou se você conseguir **ver** `reference.png` com a ferramenta de
   leitura de imagens), preencha as seções de `model_identity.md` com o que é de fato visível:
   rosto, cabelo, tom de pele, idade aparente, estilo. Não preencha o que você não viu. Mude o
   status para `APROVADA` e mantenha a frase "Esta identidade não muda entre produtos."
5. Informe que MODEL_001 está bloqueada e que `/create-video` passa a usá-la automaticamente.
