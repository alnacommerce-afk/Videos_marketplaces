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

Se MODEL_001 ainda não existe ou não tem `approved.json`: não invente uma. Avise o usuário e
ajude a criar e aprovar a modelo primeiro.

## Voz
Asset permanente em `voice_profile.json`. Preservar timbre, sotaque, idioma, personalidade,
velocidade, energia, estilo de fala, pronúncia e o gênero definido no perfil. Idioma: português
brasileiro. Se a ferramenta oferecer voice ID, voice reference, clonagem ou referência de áudio,
reutilize sempre o mesmo identificador. Voz oficial configurada tem prioridade máxima. Se a
ferramenta não conseguir usá-la: **não substituir em silêncio**; sinalizar
`VOICE_IDENTITY_NOT_AVAILABLE` e interromper a geração até haver solução válida.

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
