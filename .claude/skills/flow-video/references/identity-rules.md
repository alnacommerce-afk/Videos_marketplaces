# Identidade: modelo, voz e produto

## Modelo oficial (MODEL_001)
Armazenada de forma permanente em `assets/model/MODEL_001/`:
`reference.png` (referência oficial), `reference_front.png`, `reference_half_body.png`,
`reference_full_body.png`, `model_identity.md`, `voice_profile.json`, `approved.json`.

Depois de criada e aprovada: nunca criar outra modelo, nunca substituir, nunca "escolher outra
mulher porque combina melhor", nunca alterar a identidade facial, nunca ter pessoa diferente por
vídeo. MODEL_001 apresenta toalha, frigideira, roupa de praia, cosmético, produto pet etc.

Preservar: formato do rosto, olhos, nariz, boca, sobrancelhas, cabelo e cor, tom de pele, idade
aparente, proporções corporais, aparência e estilo geral. Deve parecer a MESMA PESSOA em todos os vídeos.

Roupa: pode mudar para combinar com produto e ambiente (praia → roupa de praia; cozinha → casual;
cosmético → casual/elegante), de forma intencional e coerente, sem alterar a identidade.

### reference.png é a fonte de verdade
`assets/model/MODEL_001/reference.png` é a referência principal da identidade e entra em todas as
cenas. `reference_front.png`, `reference_half_body.png` e `reference_full_body.png` **não** são novas
identidades: são complementares da MESMA pessoa, criadas a partir da `reference.png` e só quando
necessárias. Se uma complementar conflitar visualmente com `reference.png`, a `reference.png` vence
(e a complementar deve ser descartada ou regenerada).

Se MODEL_001 não existe ou `approved` é `false`: não invente uma. Execute `/setup-model` (ver
`model-onboarding.md`).

### MODEL LOCK
Aprovada, MODEL_001 é um asset imutável de identidade. `model_identity.md` consolida a descrição
(MODEL_ID, aparência, cabelo, rosto, idade aparente, estilo, características visuais, regras de
consistência) e registra: "Esta identidade não muda entre produtos."
`/create-video` nunca usa outra modelo enquanto MODEL_001 estiver aprovada.

## Voz (VOICE_001)
A identidade vocal faz parte da identidade da MODEL_001. Prioridade: MODEL_001 + VOICE_001 +
PRODUCT_LOCK. `voice_profile.json`:
- `voice_id: "VOICE_001"`: **identificador interno do projeto**, não um ID do Google Flow.
- `provider: "google_flow"` e `provider_voice_id: null`: o ID real do provedor, quando existir, vai
  só em `provider_voice_id`. Nunca invente um.
- `status: "pending"` até haver uma solução de voz verificada; `consistency_required: true`.

Todo prompt de cena pede: português brasileiro; mesma apresentadora; mesma voz; mesmo timbre; mesmo
sotaque; mesma personalidade; velocidade semelhante; interpretação natural. O bloco de voz é
idêntico nas 3 cenas. Não citar ElevenLabs nem outra ferramenta nos prompts.

### Requisito x capacidade
- **VOICE_REQUIREMENT:** a mesma voz em todas as cenas (requisito fixo do projeto).
- **VOICE_CAPABILITY:** o que o Flow efetivamente consegue fornecer (voice ID persistente? referência
  de áudio? só descrição textual?). Registre em `voice_profile.json` (`provider_voice_id`, `status`).
Nunca afirme que o Flow garante a mesma voz sem isso estar tecnicamente disponível. Sem voice ID
persistente, a capacidade é insuficiente para o requisito: mostre `VOICE_CONSISTENCY_NOT_GUARANTEED`
e marque `REJECTED` (a menos que o usuário verifique e confirme a consistência cena a cena).

### Voz diferente NUNCA é resultado aceitável
- Falta de `provider_voice_id` **não impede** criar roteiro, prompts, modelo ou o fluxo manual (esses
  passos seguem), mas **não garante** consistência.
- Na validação, a voz precisa soar como a mesma apresentadora nas 3 cenas. Se não soar, ou se não
  houver como verificá-lo, registre `VOICE_MISMATCH` e `VOICE_CONSISTENCY_NOT_GUARANTEED`, marque a
  cena `REJECTED` e **não aprove o vídeo final** (`final.mp4` fica como rascunho reprovado).
- Nunca aceite, em silêncio, uma voz diferente "porque ficou boa".

### Preparado para voz persistente no futuro
A skill não depende de nenhuma ferramenta de voz específica. Quando houver uma solução (voice ID do
Flow, clonagem, referência de áudio ou outra), basta preencher `provider`, `provider_voice_id` e
`status: "active"` em `voice_profile.json` e acrescentar a referência de áudio aos itens "carregar
no Flow". Prompts, fluxo e validação continuam iguais. Não adicione nenhuma agora.

## PRODUCT_CLAIM_LOCK
Roteiro, fala e legendas só podem conter:
1. características fornecidas pelo usuário;
2. informações presentes no `product.json`;
3. informações claramente visíveis na referência do produto (ex.: cor bege);
4. benefícios explicitamente informados.

Faltou informação → não invente; use abordagem neutra. Errado (sem a informação): "Essa toalha tem
ótima absorção." Certo: "Olha essa toalha de banho." / "Uma opção prática para o dia a dia."
Nunca criar números, porcentagens, propriedades, resultados, materiais, tamanhos, durabilidade,
qualidade, certificações, descontos, preços ou urgência/escassez sem dado fornecido. Adjetivos
de qualidade (macia, absorvente, resistente, premium, duradoura) são alegações e seguem a mesma regra.

Sem benefícios informados, o roteiro se apoia no que é demonstrável e visível: o que o produto é,
sua cor, o ambiente de uso, a ação de segurar/mostrar/usar. Cada linha do `script.md` indica a
fonte da afirmação (`product.json`, referência visual ou usuário). Violação =
`PRODUCT_CLAIM_VIOLATION`.

## Produto (PRODUCT_LOCK)
Antes de gerar, criar `products/PRODUCT_ID/product.json` (modelo em `assets/templates/product.json`)
com o que estiver disponível: nome, categoria, descrição, cor, quantidade, tamanho, material,
características, benefícios, preço, oferta, público, imagens de referência, informações importantes.
Não alterar deliberadamente cor, quantidade, formato, embalagem, logotipo, textura, proporção ou
características físicas. Se a informação conflitar, priorize a referência visual e os dados
explícitos do usuário.

Categorias (classificar automaticamente): cozinha, banho, casa, decoração, roupa, roupa de praia,
beleza, cosméticos, eletrônicos, pet, fitness, ferramentas, automotivo, infantil etc. Se não
estiver claro, analise imagens, nome e descrição antes de perguntar.
