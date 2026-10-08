# Análise dinâmica do produto

O sistema não guarda descrição de nenhum produto. Tudo vem da imagem do produto atual (e de dados
confiáveis que o usuário já tenha informado). Nunca reutilize cor, quantidade, estampa ou texto de
um produto anterior, nem peça ao usuário o que a imagem já mostra.

A imagem enviada é uma **entrada temporária**: depois da análise e do FRAME_MESTRE ela é removida do
projeto/Git (`master-frame.md`); ficam só os metadados em `product.json`.

## Validar a imagem
Imagem válida = arquivo `.png`, `.jpg`, `.jpeg` ou `.webp`, não vazio, que abre como imagem, e que
não é a `reference.png` da MODEL_001.
```
file --mime-type -b ARQUIVO                       # deve começar com image/
python3 -I -c "from PIL import Image; im=Image.open('ARQUIVO'); im.verify(); print(Image.open('ARQUIVO').size)"
sha256sum ARQUIVO
```
Lado menor < 600 px: avise que a fidelidade do produto pode cair, mas continue. Imagem ilegível ou
corrompida: trate como inexistente e repita o pedido de upload.

## O que extrair (quando visualmente possível; senão, "não identificado")
Nome ou tipo do produto · quantidade de unidades · cores (e qual item tem qual cor, se der para ver) ·
formato · materiais · textura · estampas · acabamento · detalhes visuais · acessórios incluídos ·
embalagem · características escritas na imagem · dimensões informadas · composição informada ·
benefícios explicitamente informados · informações que NÃO podem ser afirmadas · características que
precisam permanecer exatamente iguais.

Grave tudo em `product.json` (modelo em `assets/templates/product.json`), separando:
- **confirmado**: escrito na imagem, claramente visível ou informado pelo usuário;
- **não afirmar**: o que a imagem não mostra (preço, marca, estoque, tempo de secagem, durabilidade…
  quando não escritos), mais interpretações visuais que não são fato técnico.

## Regras
- A imagem é a fonte principal da **identidade visual do produto**. Interpretação visual não vira
  afirmação técnica (parecer "macio" na foto não autoriza dizer "macio").
- Texto escrito na imagem conta como informação explícita do anunciante e pode ser usado na fala,
  com o mesmo sentido. Prefira fatos concretos (medida, composição, quantidade). Comparativos e
  superlativos vagos ("mais eficiente", "excelente qualidade", "o melhor") só entram se literalmente
  escritos, e nunca com número ou resultado inventado.
- Infográfico: use textos, setas, ícones e selos **apenas como informação e aparência**. No vídeo não
  reproduza textos, setas, selos, ícones, molduras, elementos de interface nem o fundo artificial do
  anúncio, a menos que façam parte física do produto. Descreva no prompt só a aparência real do
  produto e inclua essa restrição.
- Informação crítica ilegível ou ambígua (quantidade, cor de cada unidade, tamanho): não invente;
  faça **uma pergunta objetiva** antes de gerar os prompts.
- Nada fixo: nenhuma frase pronta como "duas toalhas azul e bege" fora do `product.json` do próprio produto.

## Estrutura adaptada ao produto
A estrutura de 3 cenas (hook+apresentação, demonstração, desejo/uso+CTA) pode se adaptar. Demonstre
só o que é visualmente demonstrável e confirmado:
| Tipo | Demonstração |
|---|---|
| toalha/têxtil | toque, textura, tamanho, composição, uso |
| roupa | caimento, tecido, detalhes, uso (o produto veste a modelo; ver abaixo) |
| bolsa/mochila | espaço, organização, acabamento, uso |
| calçado | calçar, detalhes, solado, uso |
| cosmético | embalagem, textura, aplicação simples; sem prometer efeito na pele não escrito |
| utensílio/cozinha | uso prático e resultado visível |
| eletrônico | funcionamento, interface, benefício demonstrável; sem inventar função |
| casa/decoração/organização | uso no ambiente, encaixe, acabamento |
| ferramenta | uso seguro e prático, sem prometer desempenho não escrito |
| acessório | uso/combinação, detalhes |
Nunca use estrutura inadequada ao produto.

## Ambiente automático
Pelo contexto real de uso: toalha → banheiro · roupa → quarto/closet/ambiente de moda · bolsa →
ambiente urbano ou situação de uso · utensílio → cozinha · limpeza → ambiente doméstico adequado ·
eletrônico → ambiente compatível · ferramenta → oficina/garagem · cosmético → banheiro/penteadeira.
Nada incompatível no cenário; nenhum produto concorrente ou outro do mesmo tipo no fundo.

## Produto vestível
A modelo veste o produto no lugar da roupa-base. O microfone de lapela da MODEL_001 continua preso
no decote/gola da peça; se a peça não tiver onde prendê-lo, prenda no ponto equivalente e avise.
Rosto, cabelo e corpo seguem sempre a `reference.png`.

## Fala
Português brasileiro, natural, **18 a 24 palavras por cena** (cabe em ~8 s). Só afirmações
confirmadas. Não invente sotaque nem características pessoais da modelo; só peça "mesma voz".
