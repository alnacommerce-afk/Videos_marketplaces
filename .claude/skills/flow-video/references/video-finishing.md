# Finalização do vídeo (cortar, unir, normalizar, comprimir)

Entrega: `.mp4` pronto para postar, enviado ao usuário no chat (`SendUserFile`), **sem** ir para o Git (a menos que
o usuário peça). Trabalhe no scratchpad. Só una cenas aprovadas (`video-review.md`).

## 1. Onde cortar cada clipe
- A fala termina antes do fim do clipe; o Veo termina com um trecho borrado ou com **fusão (fantasma)**.
  Ache o fim da fala: `ffmpeg -i clip.mp4 -af silencedetect=noise=-32dB:d=0.12 -vn -f null -` (o `silence_start` final).
- Corte o vídeo e o áudio perto desse ponto (ex.: 7,5 s; 7,55 s). Confira o último quadro mantido (nitidez e sem
  fantasma): olhe quadros a cada ~0,08 s perto do corte.
- **Se a fusão final começa antes de a fala acabar** (cena 2: fusão a ~7,58 s, fala até ~7,75 s): corte o vídeo no
  último quadro limpo e **segure esse quadro** (`tpad=stop_mode=clone:stop_duration=0.28`) enquanto o áudio
  termina. Nunca corte a última sílaba.
- **Não corte no meio da fala** para tirar um defeito (close, fantasma): se não há pausa, cortaria palavras.
  Alternativas: usar como está ou regerar a cena.

## 2. Emendas
- Corte seco funciona, mas o usuário pode preferir transição. Entre cenas com continuidade (último quadro da anterior
  = primeiro da próxima) uma **fusão de 0,15 s** (`xfade=transition=fade`) fica suave (3 a 4 quadros). Mais longa
  mostra dupla exposição.
- **Mantenha a linha do tempo**: para o `xfade` não comer áudio, estenda o fim do clipe anterior com o último quadro
  clonado pela duração da fusão, e use `offset` = duração do clipe anterior. Áudio: concatene sem fusão (falas
  encavalariam) com `afade` de 0,03 s nas pontas.
- Receita (3 clipes, fusão D=0,15; tempos de exemplo):
```
[0:v]trim=0:7.50,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.15[a];
[1:v]trim=0:7.52,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.43[b];   # 0.28 de espera da fala + 0.15 da fusão
[2:v]trim=0:7.55,setpts=PTS-STARTPTS[c];
[a][b]xfade=transition=fade:duration=0.15:offset=7.50[ab];
[ab][c]xfade=transition=fade:duration=0.15:offset=15.30[v]      # 15.30 = 7.50 + 7.80 (fim do áudio do clipe 2)
```

## 3. Áudio
Normalize para **−16 LUFS, pico ≤ −1,5 dB** em duas passagens: meça (`loudnorm ... print_format=json`) e aplique com
`measured_*` e `linear=true`. Os clipes do Veo chegam com pico perto de 0 dB e médias diferentes.

## 4. Compressão para postar
`-c:v libx264 -preset slow -crf 23 -profile:v high -pix_fmt yuv420p -r 24 -movflags +faststart -c:a aac -b:a 128k -ar 48000 -ac 2`
Resultado típico: 720×1280, ~23 s, **3 a 4 MB**. 1080×1920 só se a plataforma exigir (não ganha nitidez).

## 5. Conferir antes de enviar
`ffprobe` (9:16, duração, codecs), `ffmpeg -v error -i final.mp4 -f null -` (decodifica sem erro), `ebur128` (volume), e
uma folha de contato nas emendas (sem fantasma, mesma quantidade de unidades). Diga ao usuário que você não ouve o
áudio e que ele deve ouvir as emendas.
