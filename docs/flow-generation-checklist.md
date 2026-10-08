# Checklist de geração no Flow

O Flow recebe **só o FRAME_MESTRE** (`master_frame.png`) na cena 1, e o último frame da cena anterior
(+ FRAME_MESTRE se aceitar) nas cenas 2 e 3. Não anexe a foto do produto nem a `reference.png` da modelo.
Qualquer item errado depois da cena = `REJECTED` (códigos em `references/validation.md`).

## ANTES DA CENA 1
- [ ] FRAME_MESTRE (master_frame.png) anexado
- [ ] prompt da cena 1 colado (só o bloco depois de "=== PROMPT PARA O FLOW ===")
- [ ] formato 9:16
- [ ] 8 segundos
- [ ] português brasileiro
- [ ] voz selecionada/configurada (sem voice ID persistente: `VOICE_CONSISTENCY_NOT_GUARANTEED`)

## DEPOIS DA CENA 1
- [ ] modelo correta (microfone presente)
- [ ] produto correto
- [ ] voz correta
- [ ] cenário correto
- [ ] fala correta (só o que o prompt traz; nada inventado)
- [ ] extrair último frame -> `scene_01/last_frame.png` (sem ele: `WAITING_FOR_SCENE_01_LAST_FRAME`)

## ANTES DA CENA 2
- [ ] scene_01/last_frame.png anexado (continuidade)
- [ ] FRAME_MESTRE anexado, se o Flow aceitar mais de uma imagem
- [ ] prompt da cena 2 colado

## DEPOIS DA CENA 2
- [ ] continuidade correta
- [ ] modelo correta
- [ ] produto correto
- [ ] voz correta
- [ ] extrair último frame -> `scene_02/last_frame.png` (sem ele: `WAITING_FOR_SCENE_02_LAST_FRAME`)

## ANTES DA CENA 3
- [ ] scene_02/last_frame.png anexado (continuidade)
- [ ] FRAME_MESTRE anexado, se o Flow aceitar mais de uma imagem
- [ ] prompt da cena 3 colado

## DEPOIS DA CENA 3
- [ ] continuidade
- [ ] voz
- [ ] modelo
- [ ] produto
- [ ] CTA
- [ ] português brasileiro

Vídeo final `READY` só com as 3 cenas existentes e validadas, sem nenhum código de rejeição.
