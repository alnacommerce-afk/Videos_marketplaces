# Cabo de Madeira para Espeto — Shopee (15s)

- Persona: Modelo-UGC-1 (`persona/persona.md`), não fala em cena (modo narração em voz off)
- Voz: Ainsley (Higgsfield/ElevenLabs)
- Idioma: português do Brasil
- Duração: 15s (vídeo), locução ~15,2s
- Resolução: 720p
- Foto do produto: `media_id 88d3b640-af9e-4e99-aa0a-fbcd5cad86a8`
- Foto de referência (espeto montado, para corrigir proporção da haste): `media_id 72900949-faf2-4642-bfe6-a0f16a936e8a`

## Produto

- Cabo de madeira para espeto: 13cm de comprimento, 3cm de largura (confirmado pelo usuário a partir da imagem do produto)
- Vantagens usadas no roteiro (fornecidas pelo usuário por escrito): isolamento térmico (madeira não esquenta), pegada firme e antiderrapante

## Locução (voz off)

> Esse cabo de madeira para espeto tem treze centímetros de comprimento por três centímetros de largura. A madeira não esquenta, então você segura com segurança mesmo com a brasa alta, com pegada firme e antiderrapante.

(Nenhuma característica inventada — apenas as especificações e vantagens confirmadas pelo usuário. As vantagens de reposição econômica e durabilidade, fornecidas com fontes externas, não foram usadas no roteiro por não serem atributos físicos confirmáveis do produto específico enviado.)

## Arco (8 cenas, boca sempre fechada)

1. Selfie — segura o espeto montado perto do rosto, admirando.
2. Estático wide — segura o espeto montado na vertical, mostrando o comprimento total da haste.
3. Estático macro — close no cabo isolado (sem haste), mostrando a anilha de reforço e o furo onde a haste é inserida.
4. Selfie tight — espeto montado perto do rosto, sorriso genuíno.
5. Estático — pegada firme e ergonômica no cabo, haste visível se estendendo para cima.
6. Estático macro — mão segurando o cabo perto da brasa acesa, demonstrando isolamento térmico.
7. Estático wide — apresenta o espeto montado pra câmera (pico).
8. Selfie tight — fecha com o espeto montado perto do rosto, sorriso confiante.

## Correções durante a produção (storyboard)

Essa foi a produção com mais idas e voltas até agora, porque o modelo de geração de imagem (texto-pra-imagem) errava repetidamente a geometria do produto:

1. **1ª tentativa**: haste do espeto saía curta e parecia uma lâmina/faca, não uma haste fina de espeto. Corrigido pedindo haste longa e fina como na referência.
2. **2ª tentativa**: a correção não mudou o comprimento de forma perceptível, e a haste aparecia saindo dos dois lados do cabo em alguns quadros (fisicamente incorreto).
3. **3ª tentativa**: regeneração completa do storyboard do zero, com lógica explícita de que o furo/haste ficam sempre na mesma ponta do cabo. Resultado teve nova regressão: o quadro 4 perdeu o produto inteiro, o quadro 7 voltou a mostrar duas pontas em um dos objetos, e o quadro 8 teve haste curta de novo.
4. **Resolução do storyboard**: o usuário corrigiu a imagem em outra ferramenta externa e reenviou pronta, com a haste fina, longa (proporção ~4x o cabo) e saindo de um lado só, consistente nos 8 quadros. Essa versão corrigida foi usada para gerar o 1º vídeo.
5. **Erro no 1º vídeo gerado**: mesmo com o storyboard corrigido, o vídeo (Seedance) introduziu uma pontinha de metal extra na base do cabo em alguns frames — o espeto voltava a aparecer com "duas pontas". Corrigido removendo essa pontinha da imagem de referência (nova passagem de correção) e regenerando o vídeo do zero. O 2º vídeo foi conferido frame a frame (6 frames extraídos e inspecionados) antes da entrega final, confirmando a base do cabo limpa em todos eles.

## Entregáveis

- Storyboard corrigido pelo usuário (base para o 1º vídeo): https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/25168611-7406-4d7e-94ff-1dc5ef9b0577.png
- Storyboard com a pontinha da base removida (final, usado no vídeo entregue): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20261014_145414_bf0247fd-409f-49ee-a34b-4397922dd6ed.png
- Vídeo silencioso (bruto, versão final): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20261014_151755_fd11d837-a1fa-4c9d-9a31-89fe5eceee84.mp4
- Locução (Ainsley): https://d8j0ntlcm91z4.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/hf_20261014_132156_cef34389-20c8-4119-82de-220bcb611585.mp3
- **Vídeo final (H.264/AAC, com locução):** https://d2ol7oe51mr4n9.cloudfront.net/user_3IMjRh4yp5Ie5bgUzXTv4ASGWC5/58207254-18ab-4374-bb50-079626b1e647.mp4

## Observação

Nenhuma política oficial da Shopee foi fornecida ainda — roteiro usa só as especificações confirmadas pelo usuário (13x3cm, isolamento térmico, pegada firme/antiderrapante), sem inventar nenhuma característica adicional.
