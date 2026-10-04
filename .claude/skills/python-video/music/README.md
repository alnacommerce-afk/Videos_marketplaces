# music/

Coloque aqui **somente trilhas que você tem licença para usar em anúncios/redes sociais** (compradas, de bibliotecas com licença comercial, ou criadas por você). A skill não verifica licença: quem coloca o arquivo responde por ele. O nome do arquivo usado em cada vídeo fica registrado em `audio_report.json` (pasta `_auditoria`).

Como a skill escolhe a faixa: pelo **perfil** no nome do arquivo ou da subpasta (sem diferenciar maiúsculas):

| Perfil | Quando é usado |
|---|---|
| `premium` | PREMIUM_CINEMATIC, PRODUCT_HERO, DETAIL_MACRO, GIFT_ANGLE |
| `lifestyle` | LIFESTYLE, UNBOXING, HOW_TO_USE |
| `energetic` | FAST_PACED_AD, PROBLEM_SOLUTION, BEFORE_AFTER |
| `modern` | FEATURE_SHOWCASE, PRODUCT_DISCOVERY, COMPARISON |
| `artisanal` | produtos artesanais / naturais (via LIFESTYLE) |
| `minimal` | PREMIUM_CINEMATIC, DETAIL_MACRO |

Exemplos: `music/premium/suave-01.mp3`, `music/energetic_batida.wav`. Formatos: mp3, wav, m4a, flac, ogg. Pelo menos ~20 s de duração (se for menor, repete). Ideal: 2 a 3 faixas por perfil, para os vídeos não soarem iguais; a escolha alterna entre elas.

Sem arquivo para o perfil, a skill usa a trilha **sintetizada** (original, sem copyright, mais simples).

## Corte na batida com a sua música
Para os cortes caírem na batida, escreva o BPM no nome do arquivo: `premium_92bpm_suave.mp3`, `energetic-128 bpm.wav`. A faixa deve **começar exatamente no primeiro tempo** (sem silêncio no início). Sem BPM no nome, os cortes ficam livres (o vídeo sai normalmente, só sem o travamento).
