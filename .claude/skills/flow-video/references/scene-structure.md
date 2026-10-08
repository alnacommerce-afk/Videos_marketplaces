# Cenas, ambiente, câmera e áudio

## Ambiente automático
O cenário vem do contexto real de uso e deve responder: "Por que essa pessoa usa esse produto aqui?"
CONTEXTO > BELEZA VISUAL. Nunca aleatório.
- utensílio de cozinha → cozinha · toalha → banheiro/ambiente de banho · roupa de praia → praia/piscina
- roupa social → ambiente social/elegante · pet → casa com animal quando fizer sentido
- ferramenta → oficina/garagem · cosmético → banheiro/penteadeira
- organizador → closet/cozinha/escritório conforme o produto

## Formato
Vertical 9:16, ~24s, 3 cenas de ~8s.

> Os exemplos de fala abaixo são só de tom. Antes de usar qualquer um, passe-o pelo
> PRODUCT_CLAIM_LOCK: frases com benefício ou disponibilidade só entram se houver dado que as sustente.
> Sem dados: "Olha essa toalha de banho.", "Uma opção prática para o dia a dia.", "Se curtiu, vale dar uma olhada."

## Cena 1 — Hook + apresentação
Sem introdução longa; produto aparece logo; modelo chama atenção; gancho ligado ao benefício ou
desejo. Exemplos: "Olha o que eu encontrei para deixar sua cozinha muito mais prática." /
"Se você gosta de conforto, olha essa toalha." / "Isso aqui facilita muito a rotina." Evite frases
genéricas quando houver benefício forte. Depois do hook, apresente claramente o produto.

## Cena 2 — Demonstração
Não deixe o produto parado. Use, toque, abra, vista, teste, aproxime da câmera, mostre textura,
tamanho e funcionalidade. O benefício aparece visualmente.

## Cena 3 — Conversão
Reforça o principal benefício, cria desejo, reduz dúvida, fecha com CTA natural. Exemplos:
"Se você estava procurando algo assim, vale a pena aproveitar." / "Se gostou, aproveita enquanto
ainda está disponível." / "Essa pode ser uma ótima opção para sua casa."

## Câmera
Estética de publicidade moderna para redes sociais: medium shot, close-up, product shot,
over-the-shoulder quando couber, movimentos suaves, aproximações discretas, câmera natural.
Quando a apresentadora fala para a câmera: medium shot fixo com o rosto sempre visível; "close" e "aproximação"
cortam o rosto, perdem o foco e geram fusões (dupla exposição). Sempre escrever "sem cortes, fusões, transições
ou sobreposições".

Evitar: movimento exagerado, câmera tremendo, transições artificiais, mudanças bruscas de
enquadramento, zoom excessivo.

## Áudio
Fala natural, não narrador robótico: parece uma pessoa real apresentando um produto. Prioridade:
naturalidade, clareza, ritmo, confiança, energia comercial moderada. Fala sincronizada com a ação.
Português brasileiro.

## script.md
Para cada cena: ação, enquadramento, fala, benefício (cena 3: CTA), duração.
Modelo em `assets/templates/script.md`.

## visual_bible.md
MODEL_ID, VOICE_ID, PRODUCT_ID, ambiente, iluminação, estilo, paleta, roupa, câmera,
enquadramento, regras de continuidade. Reutilizado nas 3 cenas. Modelo em `assets/templates/visual_bible.md`.
