# Revisão de um vídeo devolvido pelo Flow

Quando o usuário mandar o vídeo de uma cena, **avalie antes de liberar a próxima**. Ferramentas: `ffprobe`,
`ffmpeg`, PIL/numpy. Salve os quadros no scratchpad, nunca no repositório.

## Passos
1. Metadados: `ffprobe -show_entries format=duration:stream=codec_type,width,height,r_frame_rate` (9:16? ~8 s? tem áudio?).
2. Quadros: o primeiro, um por segundo e os últimos, e monte uma folha de contato (`hstack`/`vstack`). Olhe a folha.
3. **Primeiro quadro = quadro inicial?** `ffmpeg -i primeiro.png -i quadro_inicial.png -filter_complex "[1]scale=W:H[m];[0][m]ssim"`.
   SSIM ≥ ~0,8 e mesma pessoa/roupa/cenário = ok. Pessoa diferente = `MODEL_MISMATCH`.
4. **Conte o produto em todos os quadros** (não só no primeiro). Quantidade diferente em qualquer quadro =
   `PRODUCT_MISMATCH` (cena `REJECTED`).
5. **Nitidez do final:** variância do Laplaciano a 4 quadros/s. Se os últimos ~0,25 s caírem muito (ex.: de ~500
   para <100), é transição borrada: **não use o último quadro**.
6. Áudio: `volumedetect` e `silencedetect` (existe fala contínua?). Idioma e texto falado só dá para
   confirmar transcrevendo (ex.: nó de transcrição da ElevenLabs, com autorização e custo) ou com o
   usuário ouvindo. Sem isso, marque "fala não verificada".
7. Registre o resultado (códigos de `validation.md`) e diga o que ajustar no prompt.

## Quadro de continuidade para a cena seguinte
Nunca o último quadro literal. Use o **quadro mais nítido nos últimos ~1,0 s** (normalmente ~7,5 s de
um clipe de 8 s), com a pessoa e o produto íntegros:
```
ffmpeg -ss 7.5 -i scene_01/output.mp4 -vframes 1 scene_01/last_frame.png
```
Confira a nitidez e a quantidade de itens nesse quadro antes de usá-lo. Se o clipe foi reprovado, **não** gere
a próxima cena a partir dele: o erro (ex.: unidade a mais) se propaga.

## Lições aprendidas
- **Frames to Video mantém a modelo** (o primeiro quadro vem do FRAME_MESTRE); "Elementos/Ingredients" cria outra pessoa.
- **Separar uma unidade de um conjunto cria unidades a mais** (toalhas: de 2 para 3). Em produtos com várias
  unidades, as ações mantêm o conjunto junto (tocar, inclinar, aproximar, girar o conjunto). Nunca "desdobrar
  uma", "pegar uma" ou "separar". Escreva no prompt: "sempre exatamente N unidades, juntas nas mãos".
- **O Veo improvisa para preencher os 8 s.** Ação curta ("segura e apresenta") vira gestos inventados
  (desdobrar, virar, levantar). Escreva a AÇÃO **por faixa de tempo** (ex.: 0 a 2 s, 2 a 6 s, 6 a 8 s) e
  acrescente **"Não faz: …"** com o que não pode acontecer. Quanto menos a mão tiver o que fazer, mais
  parada deve estar a instrução ("as mãos e as toalhas ficam paradas").
- **A fala vira gesto.** Frases como "um lado é de X, o outro lado é de Y" fazem o Veo virar/mostrar os
  lados do produto. Quando a fala cita lados, faces, partes ou "por dentro", escreva na AÇÃO que isso é só
  falado e que o produto não é virado, aberto nem separado.
- A unidade extra pode aparecer **acima da pilha** em um momento e depois **ficar** (a pilha cresce). Conte as
  unidades em **cada** quadro, não só no começo.
- **Funcionou (toalha_sublimacao, prompts v4):** ação por faixa de tempo + "Não faz" + "sempre exatamente N" manteve
  **2 toalhas em todos os quadros** nos 3 clipes (antes: 3). Uma mão livre gesticular (apontar, acenar) é
  aceitável desde que não mexa no produto.
- **"Close"/"aproximação" faz zoom forte, perde o rosto e cria fusões.** Pedir "aproximação suave a um close da
  textura" gerou: close que cortou o rosto por ~2,5 s, foco perdido (nitidez caiu de ~500 para ~200) e **duas
  fusões com dupla exposição** (fantasma) a ~2 s e ~5 s. Para quem fala para a câmera, use **câmera fixa em
  medium shot, rosto sempre visível**, no máximo uma aproximação leve, e escreva "sem cortes, fusões,
  transições ou sobreposições". Procure fantasmas na folha de contato a cada 0,25 s.
- **Picos de áudio perto de 0 dB** (máx. −0,9 a −1,5 dB; média −17 a −18 dB): ao unir as cenas, normalize
  (`loudnorm`) para não estourar nem variar entre cenas.
- O Veo termina o clipe com um quadro borrado: ver "Quadro de continuidade".
- Veo 3.1 Lite entrega 720p; a modelo se manteve, mas considere um modelo melhor para o vídeo final.

## Unir as cenas (resumo; o procedimento completo está em `video-finishing.md`)
`ffmpeg -f concat -safe 0 -i lista.txt -af loudnorm -c:v libx264 -crf 18 -c:a aac final.mp4`
(cada linha da lista: `file 'scene_01/output.mp4'`). Só una cenas aprovadas. Vídeos finais pesados não vão para
o Git sem pedido do usuário.
