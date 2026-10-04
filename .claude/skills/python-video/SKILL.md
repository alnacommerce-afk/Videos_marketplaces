---
name: python-video
description: Pipeline INDEPENDENTE (Python + FFmpeg, sem IA generativa e sem gastar crédito Higgsfield) que monta vídeos comerciais 9:16 de 15–18 s a partir das fotos reais e dos fatos confirmados dos produtos da loja ALNA (store.alna.sale/loja). Câmera virtual nas fotos, motion graphics, trilha, efeitos, locução ElevenLabs opcional, quality gate com ffprobe e rotina diária de 3 vídeos pelo Windows Task Scheduler. Use sempre que o pedido for vídeo "programático", "com Python", "sem IA", "com fotos reais do produto", "slideshow profissional", "vídeo comercial da loja ALNA", "3 vídeos por dia", "rotina da madrugada" ou "salvar em Videos do Pyton" — mesmo que a pessoa não diga "python-video". NÃO use para avatar/persona UGC ou cena gerada por IA (isso é o pipeline persona/ + platforms/ com Higgsfield).
---

# python-video — comerciais programáticos da ALNA

Pipeline separado do pipeline principal (`persona/` + `platforms/`, IA generativa via Higgsfield). Aqui **nada é gerado por IA**: o vídeo é montado em código com as fotos reais do produto.

Mentalidade: diretor de criação + redator + diretor de fotografia + motion designer + editor + sound designer + engenheiro de vídeo. A pergunta nunca é "tenho 3 fotos, vou botar zoom e música", e sim: *qual é a melhor forma de apresentar ESTE produto para capturar atenção, demonstrar valor, gerar desejo e levar à ação?*

## Regras inegociáveis

1. **Veracidade.** Nunca inventar característica, material, medida, benefício técnico, certificação, garantia ou durabilidade. Só entra em vídeo:
   - **FACT**: trecho literal da página do produto (ou escrito por você no catálogo manual), guardado em `confirmed_facts` com `source`;
   - **SELLING ANGLE**: forma de organizar/apresentar um FACT. Não vira fato novo.
   Textos permitidos na tela/fala = `fact:<id>` (literal) · `name` · pergunta neutra `Já conhece {nome}?` · CTA fixo da marca · rótulo neutro do tipo do fato (Medidas, Material...). O validador recalcula cada texto a partir da fonte; texto que não bate **reprova o vídeo**.
   Afirmações sensíveis (garantia, durabilidade, "resistente", certificações, superlativos, frete grátis, desconto...) ficam `risk=true`, **não são usadas** e vão para o log. Só entram se você as confirmar por escrito no catálogo manual (`facts`).
   Informação que falta (material, medidas...) vira aviso no log: *"informação não disponível na fonte"*. Nunca é preenchida por dedução. Preço só aparece com `brand.show_price=true`.
2. **Saída sempre** MP4 · H.264 (High, yuv420p) · AAC · 1080×1920 · 30 fps · `+faststart` · 15–18 s.
3. **Nenhum vídeo é READY sem passar pelo quality gate** (`validator.py`). Falhou → FAILED, nada é entregue, tenta outro arquétipo/produto.
4. **Não alterar o pipeline principal.** Esta skill só lê/escreve dentro de `.claude/skills/python-video/` e na pasta de saída.
5. **Voz única da marca.** Uma só `ELEVENLABS_VOICE_ID`, travada em `config/voice.lock.json`; trocar exige decisão explícita.
6. **Música só com licença.** Pasta `music/` = o que *você* licenciou. Sem arquivos, a trilha é sintetizada (original, sem copyright).

## Fluxo

```
store.alna.sale ─► product_fetcher (API da loja → HTML) ─► Product Brief (fatos, imagens+papéis, estoque, ângulos)
                                              │
                         escolha do arquétipo ◄┘  (elegibilidade pelos fatos + variedade)
                                              ▼
                       storyboard.py ─► cenas: duração · imagem · câmera · transição · texto · fala · sfx · propósito
                                              ▼
              audio.py (voz ElevenLabs opcional → trilha → sfx → ducking → mix)
                                              ▼
              renderer.py (Pillow compõe → FFmpeg codifica H.264/AAC + loudnorm)
                                              ▼
              validator.py (ffprobe + conteúdo) ─► READY ─► entrega em G:\...\Videos do Pyton\AAAA-MM-DD\
```
Status por job: `QUEUED → PROCESSING → RENDERING → VALIDATING → READY | FAILED` (`work/<dia>/<job>/status.json`).

## Executar manualmente

```bash
cd .claude/skills/python-video/scripts
# 1 vídeo, a partir do catálogo manual (fotos locais + fatos confirmados por você)
python build_video.py --catalog ../templates/catalog.example.json --product exemplo-001 --voice off
# 1 vídeo direto da página do produto na loja
python build_video.py --url https://store.alna.sale/produto/<slug> --archetype PREMIUM_CINEMATIC
# só ver o que a loja devolve
python product_fetcher.py discover
python product_fetcher.py brief https://store.alna.sale/produto/<slug>
# só o storyboard (sem render)
python storyboard.py <brief.json> --archetype FEATURE_SHOWCASE
# a rotina do dia (os 3 vídeos), na mão
python scheduler.py run-daily
```

Operação diária e primeira instalação:
```bash
python doctor.py --smoke            # confere o PC (Python, FFmpeg, Drive, loja, tarefa...) e gera 1 vídeo de teste
python product_fetcher.py diagnose  # relatório da loja real + HTML bruto em logs/diagnostico-loja/ (me envie o .txt)
python feedback.py review           # lista os vídeos de hoje (arquétipo, música, gancho, onde assistir)
python feedback.py add video_01 4 "comentário"   # nota 1–5 por vídeo (semana supervisionada)
python feedback.py summary          # médias por arquétipo / música / gancho
python notify.py test               # testa o aviso (Telegram / e-mail)
```
Opções úteis: `--voice auto|off|required` · `--format 9x16|4x5|1x1|16x9` · `--out PASTA` · `--no-deliver` · `--seed N`.

## Fonte dos produtos (como a loja é lida)

Ordem automática: **catálogo manual** (`--catalog`) → **API pública da própria loja** → **páginas HTML** (plano B se a API falhar).
- **API da loja** (`config.store.supabase`): a mesma API que o site usa no navegador, com a chave *publishable* (feita para ficar no navegador e limitada pelas regras RLS: só vê produtos **publicados**, suas fotos e variações). Uma única consulta traz título, descrição **com as linhas originais**, fotos na ordem, texto alternativo das fotos, preço e **estoque**. Nunca coloque a chave `service_role` aqui.
- **Estoque:** produto com estoque 0 não recebe vídeo (`daily.skip_out_of_stock`). Só a API informa estoque; no plano B (HTML) não dá para saber.
- **Fatos da descrição:** lidos **linha a linha**. Cada linha vira um fato literal (`Tamanho: 70 x 130 cm`, `Composição: Algodão com Poliéster`, `Ideal para praia, piscina...`). Títulos e perguntas (`Para quem é?`, `Dois lados, duas funções`) **não viram fato**; `Observação:`/`Importante:` ficam registradas e **não são usadas**; medidas sob "aproximadas" aparecem como `Aprox. ...`; números sem unidade e comparativos não verificáveis (`melhor adaptação`) ficam retidos.
- **Fotos:** o texto alternativo publicado na loja ("Close na textura…", "Pessoa usando…", "Embalagem… presente") define o **papel** da foto (`detail`, `lifestyle`, `packaging`, `product`). Planos de detalhe/macro preferem fotos `detail`; o segundo detalhe segue o arquétipo (LIFESTYLE/DEMONSTRATION/HOW_TO_USE → `lifestyle`; UNBOXING/GIFT → `packaging`); planos hero usam sempre a capa. O papel só escolhe **enquadramento**: nunca vira afirmação sobre o produto.
- `python product_fetcher.py diagnose` mostra o que a API e o HTML devolvem e como os fatos foram classificados; `--source html|api|auto` força a fonte.

## Rotina automática (3 vídeos por madrugada)

`scheduler.py run-daily` é disparado pelo **Windows Task Scheduler** (não é loop infinito): **02:00** (principal) e **05:00** (recuperação). É idempotente: só produz o que falta no dia.
- Escolhe 3 produtos (nunca/menos usados primeiro, cooldown de 10 dias), 3 arquétipos diferentes, ganchos e trilhas diferentes.
- Falhou? Até 3 tentativas por vídeo, **cada uma com outro arquétipo**; depois troca de produto. Faltou produto? Registra e **não inventa conteúdo**.
- **Retomada após desligamento:** se o PC estava desligado às 02:00, a tarefa roda assim que ele ligar (`StartWhenAvailable`) e produz o que falta do dia, mesmo depois das 08:00 (marcado como `late` no resumo; `daily.catch_up_after_deadline=false` volta a bloquear depois das 08:00). Queda de energia no meio da produção: a trava é considerada abandonada (processo morto ou criada antes do último boot), cópias `.partial` são limpas e o vídeo interrompido recomeça do zero. Dias passados não são recuperados.
- Entrega por cópia atômica (`.partial` → rename). Se o Drive estiver fora do ar, o vídeo fica READY em `work/` e a entrega é refeita na execução seguinte.
- Instalar: `scripts\install_windows.ps1` (Python, FFmpeg, venv, dependências, teste e tarefa). Ou só a tarefa: `python scheduler.py install-task` (gera `config\ALNA-PythonVideo-Diario.xml`).
- **Dependências físicas** (documentadas, não dá para garantir por software): o PC precisa estar **ligado ou em suspensão com "permitir temporizadores de ativação"**, com **o usuário logado** (bloqueio de tela é ok — a tarefa roda "somente quando o usuário está conectado" porque o `G:` do Google Drive é por usuário), com **Google Drive para computador aberto e sincronizando**, e com internet. PC desligado = sem vídeos.

## Técnicas de estrutura (estilo "spec ad": ritmo, continuidade e som)

Pensadas para fotos (sem filmagem) e para Reels / vídeo dos marketplaces. Todas têm checagem no quality gate.

| Técnica | Como funciona aqui | Checagem |
|---|---|---|
| **Continuidade de movimento** (movement match) | A direção do pan/diagonal é herdada da cena anterior; entre os movimentos permitidos a cena prefere o que continua o impulso (eixo e sentido). Whip/motion/wipe saem no mesmo sentido em que a câmera vinha. Match cut (quando a mesma foto repete) retoma exatamente do enquadramento anterior. | `continuidade de movimento` (≤ 1 inversão de pan) |
| **Ponte sonora** (J-cut) + **textura contínua** | Cada cena tem uma cama sonora discreta (ambiente grave nos planos abertos, "ar" nos detalhes, micro cliques no macro) que **entra 0,25 s antes do corte** e cruza com a anterior. O vídeo nunca fica em silêncio. | `pontes sonoras`, `áudio nunca em silêncio` |
| **Corte na batida** (beat-lock) | Toda troca de cena e o fim do vídeo caem num tempo forte da trilha. Na trilha sintetizada o andamento varia até ±10% para achar a grade que menos desloca os cortes; o impacto/kick cai exatamente no corte. Respeita cena ≥ 1,2 s, a narração e 15–18 s. Em música sua, só trava se o nome tiver o BPM (`premium_92bpm.mp3`, faixa começando no tempo 1); sem BPM os cortes ficam livres e o log avisa. | `cortes na batida` (erro ≤ meio quadro) |
| **Crescendo** | A trilha sintetizada começa mínima (pad) e acumula melodia → baixo → percussão; o ápice é o CTA. A curva de energia é monotônica e começa mais baixa em ritmo lento. Em música sua é uma rampa de volume (−4 dB → 0 dB). | `trilha cresce até o clímax` (≥ 3 dB, só na sintetizada) |

Não implementado de propósito: relógios/time-remap com urgência (pode sugerir escassez que o produto não tem) e narrativa de identidade/"ritual" sem fatos de uso confirmados por escrito (item 7, aguardando decisão).

## Clipes de ambiente (b-roll, Pixabay)

Cortes curtos (≈2–3 s) de vídeo livre que **ilustram um uso que a loja já confirma**, para o vídeo não ser só foto. Opcional: sem chave, sem tema ou sem rede, o vídeo sai só com as fotos.

- **Chave (duas formas, nesta ordem):** (1) variável de ambiente `PIXABAY_API_KEY`; (2) um arquivo de texto **`APIpixabay`** (pode ser `APIpixabay.txt`, o Bloco de Notas esconde a extensão) na pasta da skill, com a chave dentro. O arquivo aceita só a chave, `chave: XXXX` ou `key=XXXX`, com comentários e linhas extras, em UTF-8/UTF-16/ANSI. Chave gratuita em pixabay.com/api/docs.
  - **Segurança:** o arquivo está no `.gitignore` (`APIpixabay*`, `*.key`, `.env`), os logs e mensagens de erro escondem qualquer `key=...`, e um teste falha se uma chave aparecer em arquivo do projeto. O `doctor` mostra **de onde** a chave foi lida, nunca o valor.
  - **Cuidados seus:** não zipe nem envie a pasta da skill com o arquivo dentro; se a chave for exposta (colada em conversa, e-mail), use o botão *Rotate* na página da API e atualize o arquivo. Não criptografamos o arquivo de propósito: sem uma proteção do sistema, a "criptografia" com a chave ao lado seria só aparência. Para chaves de acesso pago (ElevenLabs) o ideal é a proteção do próprio Windows (DPAPI), que podemos adicionar.
- **Tema:** sai só de palavras de fatos confirmados do tipo `use` ("Ideal para **praia, piscina, academia, viagens**") → temas `praia`, `piscina`, `academia`, `viagem`, `caminhada`, `danca`, `cozinha`, `banho`, `yoga`, `camping`, `jardim`. Frase de marketing que não é fato de uso não gera busca. A busca usa `lang=pt` e cai para inglês.
- **Regras de segurança (reprovam o vídeo se violadas):** o texto da cena é o fato de USO literal (nunca material/medida/característica); rótulo **"Imagem ilustrativa"** visível; origem (id, autor, link) registrada; no máximo `broll.max_per_video` (1); tags com criança/bebê são descartadas; clipe cujas tags batem com o próprio produto (ex.: `towel` numa toalha) é descartado, porque mostraria **outro** produto.
- **Onde aparece:** arquétipos PRODUCT_HERO, FEATURE_SHOWCASE, BENEFIT_SHOWCASE e PRODUCT_DISCOVERY têm uma cena opcional `AMBIENT` que some quando não há clipe; LIFESTYLE, DEMONSTRATION e HOW_TO_USE já têm cena de uso.
- **Formato:** vertical preenche o quadro; horizontal 4K recorta um vertical nítido; horizontal menor fica centralizado sobre uma cópia desfocada. O áudio do clipe é ignorado.
- **Termos da API:** cache de 24 h e **sem download em massa** (busca só o que usa e guarda cada clipe em `cache/broll/`); a API pede mostrar a origem quando se exibem *resultados de busca* (não é o caso aqui), e `creditos.txt` (em `_auditoria`) traz o texto de crédito para quem quiser usar na legenda. Confirme a licença atual no site do Pixabay.

### Vídeo de demonstração (`--demo`): para AVALIAR o visual com clipes

```
..\.venv\Scripts\python.exe build_video.py --slug toalha-de-capivara-70x130-200g --demo --voice off
```
Gera um vídeo que **alterna fotos reais do produto e até 3 clipes do Pixabay** (arquétipo `DEMO_MIX`: clipe → foto do produto → detalhe → clipe com o texto do uso → detalhe → clipe → CTA), com efeitos sonoros nas trocas e textos animados. A busca usa "produto + tema" (ex.: `towel beach`) para trazer **pessoas usando um produto parecido**. Sai em `teste\AAAA-MM-DD\` (dentro da pasta da skill), nunca no Drive.
- **Só para avaliação.** O clipe mostra um produto *parecido*, não o da loja: toda cena de clipe leva "Imagem ilustrativa" e o `creditos.txt` registra "MODO DEMONSTRAÇÃO". Antes de publicar algo assim, decida com a política de cada marketplace e a regra de publicidade do consumidor.
- **A rotina diária nunca usa o modo demo:** ela mantém 1 clipe, bloqueia produto parecido e crianças, e o `DEMO_MIX` só é elegível com ≥ 2 clipes.
- Cena de clipe sem texto é permitida (o clipe aponta, em `clip.fact_id`, o fato de uso que o justifica; o gate confere). Só um clipe por vídeo leva o texto do fato de uso.

## Semana supervisionada (primeira semana de produção)

Nos primeiros ~7 dias, assista aos vídeos e avalie cada um com `feedback.py` (nota 1–5 + comentário). O objetivo é descobrir o que o público-alvo aprova antes de automatizar mais (ex.: publicação). Perguntas guia: o gancho prendeu nos 2 primeiros segundos? O produto está claro e dominante? O texto está legível? A trilha combina? Você postaria? Depois da semana, `feedback.py summary` mostra quais arquétipos, músicas e ganchos funcionam, e ajustamos `archetypes.json`/`styles.json`.

## Onde ficam os arquivos

| O quê | Onde |
|---|---|
| Vídeos | `G:\Meu Drive\DRIVE - COMPUTADOR\MARKETING\Videos do Pyton\AAAA-MM-DD\video_01_<produto>.mp4` |
| Auditoria (brief, storyboard, roteiro, validação, relatórios, folha de contato) | `...\AAAA-MM-DD\_auditoria\video_01_<produto>\` |
| Jobs de trabalho / estado da rotina | `work/` (`state.json` guarda histórico anti-repetição) |
| Logs | `logs/AAAA-MM-DD.jsonl` (cada evento) e `logs/daily-AAAA-MM-DD.json` (resumo) |
| Cache de HTML/imagens/locução | `cache/` |

Log por vídeo: timestamp, produto, URL, arquétipo, roteiro, duração, início/fim do render, resultado, erro, caminho final.

## Configuração

- `config/config.json` — formato e safe areas, duração, pastas, loja, rotina, marca/CTA, fontes, áudio, ElevenLabs, encode. Variáveis de ambiente sobrescrevem pastas: `ALNA_OUTPUT_DIR`, `ALNA_MUSIC_DIR`, `ALNA_WORK_DIR`, `ALNA_CACHE_DIR`, `ALNA_FONTS_DIR`, `ALNA_LOGS_DIR`.
- `config/archetypes.json` — biblioteca de 15 arquétipos (estrutura narrativa, ritmo, trilhas compatíveis, `requires`).
- `templates/styles.json` — estilos visuais (clean, dark, warm, bold). `templates/catalog.example.json` — catálogo manual.
- **Formatos**: 9:16 (padrão, 1080×1920) · 4:5 · 1:1 · 16:9, cada um com safe area própria (9:16: topo 250, base 480, direita 150, esquerda 64 px).

### ElevenLabs (locução opcional)
```powershell
setx ELEVENLABS_API_KEY  "sua-chave"          # nunca grave a chave em arquivo do repositório
setx ELEVENLABS_VOICE_ID "id-da-voz-oficial"  # escolha UMA voz pt-BR e mantenha
```
Reabra o terminal. Sem as duas variáveis o vídeo sai **sem narração** (texto + trilha) e o log avisa; use `--voice required` para falhar em vez disso. Atenção: contas ElevenLabs sem plano que libere vozes da biblioteca só podem usar as vozes liberadas para a conta (já ocorreu neste repo, ver `persona/persona.md`); escolha uma voz brasileira que a conta consiga usar de fato. Números/medidas são ajustados para a pronúncia (`80x150cm` → "80 por 150 centímetros").

### Aviso ao terminar a rotina (opcional)
`logs/ultimo-resumo.txt` é sempre gravado. Para receber no celular, configure **um** canal (detalhes no topo de `scripts/notify.py`):
- Telegram: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
- E-mail: `ALNA_SMTP_HOST`, `ALNA_SMTP_USER`, `ALNA_SMTP_PASSWORD` (Gmail: senha de app) e `ALNA_NOTIFY_TO`.
O aviso diz quantos vídeos ficaram prontos, quais, se rodou atrasado e o que falhou. Falha no aviso nunca derruba a rotina.

### Fontes
Prioridade: Inter, Montserrat, Poppins, Manrope, DM Sans, Archivo, Roboto, Segoe UI, Arial, Liberation Sans, DejaVu Sans — usa a primeira instalada. A **Inter Bold** (licença OFL) já vem em `fonts/`. Para outra identidade, coloque outro `.ttf` ali e ajuste a ordem em `config.json`.

### Música
Coloque faixas **licenciadas por você** em `music/` (guia em `music/README.md`); o perfil é reconhecido pelo nome do arquivo ou da subpasta: `premium`, `lifestyle`, `energetic`, `modern`, `artisanal`, `minimal` (ex.: `music/premium/suave.mp3`). Sem arquivo para o perfil, usa a trilha sintetizada.

## O que o diretor (você, Claude) deve fazer ao usar esta skill

1. Leia o brief antes de decidir: quais fatos existem? O arquétipo é escolhido entre os **elegíveis** (ex.: `GIFT_ANGLE` só com fato de presente confirmado; `HOW_TO_USE` só com fato de uso).
2. Gancho nos primeiros 2–3 s (Reels e vídeos de marketplace são julgados nos primeiros segundos): mostre o produto ou um detalhe/pergunta neutra — nada de "Conheça nosso produto...". Estilos: `fact_hook`, `name_reveal`, `question`, `silent_macro`.
3. Hard cut é o padrão; transição só com função narrativa (dissolve = passagem de tempo/calma, whip/motion = energia, zoom/match cut = continuidade, wipe = lista de itens, light sweep = premium).
4. Texto curto: um por cena, produto sempre dominante. Não crie elemento gráfico para preencher espaço.
5. Se um produto não tem fatos suficientes, **pule-o** e registre. Se faltar uma informação importante, **pergunte ao usuário** em vez de assumir.
6. Depois de gerar, abra `video.contact.jpg` (folha de contato) e confira o visual além do relatório de validação.

## Quality gate (resumo)

Técnico: arquivo existe/abre, H.264, yuv420p, AAC, 1080×1920, 30 fps, duração 15–18 s = storyboard, áudio≈vídeo (±0,15 s), `moov` antes de `mdat`, decodificação sem erros, tamanho, loudness ≈ −14 LUFS e true peak seguro.
Conteúdo: produto/imagens do brief, **todo texto rastreável a um fato**, texto na safe area, tamanho ≥ 4% da largura, contraste ≥ 3:1, CTA visível ≥ 1,2 s, narração não cortada, ducking ≥ 6 dB, voz ≥ 12 dB acima da trilha, primeiro quadro não preto, quadros não vazios, cenas distintas.

## Arquitetura

```
scripts/common.py          config, logs JSONL, máquina de status, ffprobe
scripts/product_fetcher.py loja → Product Brief (JSON-LD / JSON embutido / OG; robots; cache; fatos; risco)
scripts/camera.py          pontos de interesse, planos (hero/detail/macro), movimentos, easing
scripts/storyboard.py      elegibilidade, arquétipo, cenas, textos rastreáveis, retime p/ locução
scripts/graphics.py        fontes, cards, lower third, callout, CTA, badge, máscaras, animações de texto
scripts/audio.py           ElevenLabs, trilha, sfx sintéticos, ducking, mix, loudnorm
scripts/renderer.py        composição por quadro, transições, FFmpeg (H.264/AAC)
scripts/validator.py       quality gate
scripts/build_video.py     orquestra 1 vídeo (CLI)
scripts/scheduler.py       rotina diária + Task Scheduler
scripts/doctor.py          checagem do PC + vídeo de teste (--smoke)
scripts/feedback.py        notas por vídeo na semana supervisionada
scripts/notify.py          aviso ao terminar (Telegram / e-mail)
scripts/install_windows.ps1 instalação no Windows
tests/                     testes (python tests/test_pipeline.py [--fast])
```
Por que Pillow+FFmpeg e não MoviePy/OpenCV: Pillow dá controle por quadro (câmera, texto, máscaras) e o FFmpeg faz o que faz melhor (codificação, loudnorm). MoviePy/OpenCV não trariam benefício real e aumentariam dependências. Dependências: `Pillow`, `numpy`, `requests` (`requirements.txt`) + FFmpeg no PATH.

Movimentos: push-in, pull-out, pan H/V, diagonal, dolly (ease in-out), crop reveal (pull-out de macro), parallax (fundo desloca mais devagar), foco (rack focus) · Transições: hard cut (padrão), match cut, dissolve, fade, zoom, motion, whip (com motion blur), mask reveal, directional wipe, blur, speed ramp, light sweep · Motion: fade, slide, scale, mask reveal, word reveal, staggered, kinetic typography, tracking.

## Troubleshooting

| Sintoma | Causa provável / solução |
|---|---|
| `API da loja indisponível` | O pipeline cai sozinho para o HTML (veja o aviso no log). Se for chave errada: confira `config.store.supabase.publishable_key` ou a variável `ALNA_SUPABASE_KEY`. |
| Sem clipes de ambiente | `python doctor.py` mostra de onde a chave do Pixabay foi lida (variável ou arquivo `APIpixabay`); veja no log `b-roll indisponível` / `nenhum clipe adequado`. |
| `Nenhum produto encontrado em .../loja` | A API falhou e o HTML não traz produtos. Use `python product_fetcher.py diagnose` ou `--catalog`. |
| `robots.txt não permite` | Respeitamos o robots.txt. Use catálogo manual. |
| `'ffmpeg' não encontrado` | `winget install Gyan.FFmpeg` e reabra o terminal. |
| Vídeo sem narração | `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` ausentes (veja o log) ou `--voice off`. |
| `difere da voz oficial travada` | Mantenha a voz da marca; para trocar de propósito apague `config/voice.lock.json`. |
| `Reprovado no quality gate: ...` | Leia `work/<dia>/<job>/validation.json`; o job fica FAILED e nada é entregue. |
| Não sei se o PC está pronto | `python doctor.py --smoke` |
| Loja não lida / produtos errados | `python product_fetcher.py diagnose` e envie `logs/diagnostico-loja/store-diagnostic.txt` |
| Vídeos não aparecem às 08:00 | PC desligado/sem login/Drive fechado. Veja `logs/daily-AAAA-MM-DD.json` e `Get-ScheduledTaskInfo -TaskName ALNA-PythonVideo-Diario`. |
| Texto "estranho" na pronúncia | Ajuste `speakable()` em `audio.py`. |
| Visual com fonte genérica | Instale Inter/Montserrat em `fonts/`. |
