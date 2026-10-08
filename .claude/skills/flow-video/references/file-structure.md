# Estrutura de arquivos (na raiz do projeto)

```
assets/model/MODEL_001/
  reference.png  reference_front.png  reference_half_body.png  reference_full_body.png
  model_identity.md  voice_profile.json  approved.json
products/PRODUCT_ID/
  product.json
  master_frame.png       (FRAME_MESTRE: a única imagem de partida do Flow)
  visual_bible.md
  script.md
  scene_01/  prompt.txt  output.mp4  last_frame.png
  scene_02/  prompt.txt  output.mp4  last_frame.png
  scene_03/  prompt.txt  output.mp4
  final/final.mp4
  validation.md          (códigos de rejeição por cena)
```
`approved.json`: `{"approved": false|true, "model_id": "MODEL_001", "approved_at": null|"AAAA-MM-DD"}`.
`voice_profile.json`: ver `identity-rules.md`.

`products/_inbox/` (fixa): destino do upload no GitHub. Após `ENVIEI` a imagem original é entrada **temporária**: movida para `products/PRODUCT_ID/references/` durante o processamento e **removida do Git** no fim (fica só `master_frame.png` e metadados em `product.json`). Produtos antigos podem ainda ter `references/` com a original.

Variantes: `products/PRODUCT_ID/variants/A|B|C/` com a mesma estrutura de cenas e final.
