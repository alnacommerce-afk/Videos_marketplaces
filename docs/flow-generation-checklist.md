# Checklist de geração no Flow

Prioridade das referências: 1) `MODEL_001/reference.png` (identidade da modelo) · 2) último frame da
cena anterior (continuidade) · 3) foto do produto (identidade do produto).
Qualquer item marcado errado depois da cena = `REJECTED` (códigos em `references/validation.md`).

## ANTES DA CENA 1
- [ ] MODEL_001/reference.png carregada
- [ ] produto carregado
- [ ] prompt da cena 1 carregado
- [ ] formato 9:16
- [ ] 8 segundos
- [ ] português brasileiro
- [ ] voz selecionada/configurada (sem voice ID persistente: `VOICE_CONSISTENCY_NOT_GUARANTEED`)

## DEPOIS DA CENA 1
- [ ] modelo correta
- [ ] produto correto
- [ ] voz correta
- [ ] cenário correto
- [ ] fala correta (só o que o prompt traz; nada inventado)
- [ ] extrair último frame -> `scene_01/last_frame.png` (sem ele: `WAITING_FOR_SCENE_01_LAST_FRAME`)

## ANTES DA CENA 2
- [ ] MODEL_001/reference.png
- [ ] produto
- [ ] scene_01/last_frame.png
- [ ] prompt cena 2

## DEPOIS DA CENA 2
- [ ] continuidade correta
- [ ] modelo correta
- [ ] produto correto
- [ ] voz correta
- [ ] extrair último frame -> `scene_02/last_frame.png` (sem ele: `WAITING_FOR_SCENE_02_LAST_FRAME`)

## ANTES DA CENA 3
- [ ] MODEL_001/reference.png
- [ ] produto
- [ ] scene_02/last_frame.png
- [ ] prompt cena 3

## DEPOIS DA CENA 3
- [ ] continuidade
- [ ] voz
- [ ] modelo
- [ ] produto
- [ ] CTA
- [ ] português brasileiro

Vídeo final `READY` só com as 3 cenas existentes e validadas, sem nenhum código de rejeição.
