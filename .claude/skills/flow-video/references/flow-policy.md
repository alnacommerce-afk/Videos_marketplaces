# Políticas e bloqueios do Google Flow (Veo)

Origem: o Flow bloqueou a cena 1 com a mensagem "Esse comando pode violar nossas políticas contra a
geração de imagens de pessoas famosas" (reembolsa a geração). Pesquisa feita em 2026-10-08.
As páginas oficiais não puderam ser abertas deste ambiente (domínios bloqueados); o que segue vem de
trechos de resultados de busca. **Confiança: média.** Reverifique nas páginas oficiais quando possível:
Flow Help (support.google.com/flow), FAQ do Flow, Generative AI Prohibited Use Policy e a página
"Responsible AI and usage guidelines" do Veo no Google Cloud.

## O que se sabe
- **Oficial (Flow Help):** o Flow tem salvaguardas para menores e para **fotos enviadas de pessoas**;
  algumas consultas podem não ser geradas. Bloqueios inesperados: use o feedback do próprio Flow.
- **Oficial/semioficial:** não se pode usar imagens de celebridades, políticos ou figuras públicas. A
  documentação do Veo descreve filtros para "representação fotorrealista de pessoa proeminente" e
  triagem da imagem de entrada.
- **Falsos positivos são comuns** (fóruns do Google): imagens de pessoas fotorrealistas, até geradas por IA,
  e retratos comerciais comuns são bloqueados. Pode depender de região e do modelo (Veo 3.1).
- Em vídeo a partir de imagem, **a imagem de partida é a primeira suspeita**, o texto vem depois.

## Regras para os prompts (texto)
1. Sem nome de pessoa real nem "no estilo de".
2. Não mande "copiar/preservar exatamente o rosto/identidade de uma pessoa". Peça **consistência
   de aparência** ("mesma aparência de cena em cena: cabelo, roupa e proporções") e deixe a imagem
   carregar o rosto.
3. Evite "pessoa real", "idêntica", "semelhante a", "deepfake", "identidade facial", tom de pele/idade.
4. Evite marcas e logos no texto (ex.: nome do fabricante do microfone); a imagem já mostra o objeto.
5. Descreva a ação, o produto e o ambiente; não descreva traços faciais.
6. Se for **verdade**, pode acrescentar: "personagem apresentadora original da marca, sem semelhança
   com nenhuma pessoa famosa ou figura pública". Nunca use essa frase para mascarar o rosto de uma
   pessoa real, nem sem ter certeza.

## Diagnóstico (descobrir se o bloqueio vem da imagem ou do texto)
- **Teste A:** a mesma imagem de partida + prompt curto neutro: "A apresentadora segura duas toalhas
  brancas e sorri para a câmera." Bloqueou → o problema é a imagem; reescrever o texto não resolve.
- **Teste B:** a mesma imagem + o prompt completo v2. Se A passa e B bloqueia, o texto é o problema:
  corte seções até achar.
- Anote modelo (Veo 3.1 rápido/qualidade), modo (Frames to Video ou Ingredients) e o texto exato do erro.
- Desligue qualquer "melhorar/otimizar prompt" automático do Flow, se existir.

## Se a imagem for o problema
- Use o botão de feedback/sinalizar do Flow no bloqueio, com o texto do erro.
- A personagem é fotorrealista, então o filtro pode confundi-la com alguém público: não há ajuste de
  prompt legítimo que resolva. Caminhos legítimos: (a) reportar o falso positivo ao Google;
  (b) tentar outro frame inicial com a mesma composição; (c) testar a mesma imagem no Veo por outra
  via (ex.: nó Veo 3.1 dentro da ElevenLabs), que usa os mesmos filtros do Google e pode se comportar
  diferente; (d) pedir liberação ao Google para uso com consentimento.

## O que NUNCA fazer
- Não pixelar, distorcer ou alterar o rosto só para passar do filtro, nem usar técnicas de burlar.
- Não usar a imagem de uma pessoa real sem consentimento. Se a MODEL_001 é uma pessoa real, o uso
  precisa de autorização dela; se é uma personagem gerada por IA, diga isso ao Google no feedback.
- Não apresentar o bloqueio como "bug" para forçar: se persistir, é decisão de política.

## Modo do Flow (lição da toalha_sublimacao)
Com o FRAME_MESTRE como **imagem de referência (Ingredients)**, o Flow gerou **outra mulher** (cabelo longo,
blusa estampada, outra cozinha): reaproveitou só microfone e toalhas. Em referência, o Flow não replica
pessoas de fotos enviadas. Use **Frames to Video com o FRAME_MESTRE como quadro inicial**: o vídeo
parte do quadro e mantém a pessoa. Descreva só cabelo e roupa no texto (sem traços do rosto). Sempre
confira o primeiro quadro do resultado. Pessoa diferente = `MODEL_MISMATCH` (cena `REJECTED`).
