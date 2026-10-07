# Estrutura de arquivos (na raiz do projeto)

```
assets/model/MODEL_001/
  reference.png  reference_front.png  reference_half_body.png  reference_full_body.png
  model_identity.md  voice_profile.json  approved.json
products/PRODUCT_ID/
  product.json
  references/
  visual_bible.md
  script.md
  scene_01/  prompt.txt  output.mp4  last_frame.png
  scene_02/  prompt.txt  output.mp4  last_frame.png
  scene_03/  prompt.txt  output.mp4
  final/final.mp4
```
Variantes: `products/PRODUCT_ID/variants/A|B|C/` com a mesma estrutura de cenas e final.
