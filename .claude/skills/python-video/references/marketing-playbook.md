# Playbook de marketing (CMO) — vídeos de produto ALNA

Papel: o Claude é o CMO; o dono é o CEO; o "time de execução" é este computador (Python + FFmpeg + APIs). Este arquivo guarda o conhecimento para decidir **o que** o vídeo comunica e **como**, antes de qualquer comando técnico. Atualize-o a cada aprendizado (notas do dono, métricas, referências).

## 1. Objetivo e regras que não mudam
* Objetivo de cada vídeo: **conexão → credibilidade → confiança → (compra no próprio marketplace)**.
* Nunca inventar característica, número, prova social ou urgência. Só fato confirmado (loja, `config/user_confirmed.json`, dono por escrito).
* Vídeo para marketplace: **sem chamada para fora** (loja, link, site, redes, contato) e sem texto promocional que a plataforma puna. A ação é nativa: o comprador já está na página do produto. (`brand.marketplace_safe`)
* Cada marketplace tem política própria de vídeo: conferir e registrar em `platforms/*/policy.md` antes de publicar em larga escala.

## 2. Atenção em segundos (mídia exterior digital + Reels)
* Mensagem de relance: 5–7 palavras (≤ 5 quando o olhar dura 2–3 s); uma ideia por cena; alto contraste; texto grande.
* Gancho: valor/curiosidade nos primeiros ~3 s, texto na tela logo no primeiro segundo (muita gente assiste sem som).
* Estrutura de resposta direta: gancho → benefício/prova → fechamento; fechar o ciclo antes do fim.
* Fontes consultadas: dicas de criativo DOOH (doohmarketing.com, adquick.com) e guias de gancho TikTok/Reels (sovran.ai, houseofmarketers.com).

## 3. Persuasão com honestidade
| Princípio | Como usamos (sem inventar) |
|---|---|
| Especificidade | medida, material, conteúdo reais ("70 × 130 cm") em vez de adjetivo |
| Prova | só o que existe: fatos da loja; nunca "mais vendido", "avaliações" sem dado |
| Escassez/urgência | só com dado real (estoque baixo vindo da loja) |
| Pico-fim (peak-end) | o melhor plano no meio e um fechamento forte e limpo (nome do produto) |
| Pattern interrupt | corte/whip no início, clipe humano de uso antes do produto |
| Identificação | cena do uso real ("para as crianças na praia") dirigida ao **adulto** que compra |
| Aversão à perda / reciprocidade | não usadas sem base real |

## 4. Storytelling (3 atos com fatos confirmados)
* **Ato 1 — momentos de uso** (conexão): cada fato de USO vira um capítulo curto (praia, escola, casa...).
* **Ato 2 — o produto** que reúne esses momentos (revelação do nome).
* **Ato 3 — prova e fechamento**: fatos (medida/material) e o nome do produto.
* Arquétipo `DEMO_MIX` (demo) e `CONNECT_TRUST` (rotina). O que torna história: sequência com tensão/alívio (cortes mais rápidos → respiro no produto), música em crescendo, texto que muda de "voz" conforme o momento (kit de tipografia).

## 5. Linguagem visual
* Preencher o quadro 9:16: clipes horizontais entram em **cover + pan** (sem faixas); fotos de estúdio se dissolvem no fundo com degradê largo.
* Texto: kit tipográfico (`scripts/textkit.py`): marcador, serifa itálica, contorno/black, fita inclinada, mono, itálico com destaque; palavra-chave destacada; modelo escolhido conforme a transição da cena e nunca repetido em seguida. Riscado (taxado) só com um "antes" real.
* Crianças: apenas em clipes ilustrativos do `--demo`, com uso infantil confirmado; texto fala com o adulto (Conanda 163/2014; CONAR art. 37). Sem selo na imagem (decisão do dono); a origem fica em `creditos.txt`.

## 6. Mapa de ferramentas (quem faz o quê)
| Necessidade | Ferramenta | Estado |
|---|---|---|
| Montar, animar, codificar | Python + Pillow + FFmpeg (este PC) | ativo |
| Clipes de uso real | Pixabay API (chave em `API\`) | ativo |
| Voz/narração | ElevenLabs (chave em `API\`; falta `voice_id`) | opcional |
| Efeitos sonoros/trilha | sintetizados (sem copyright); ElevenLabs tem geração de efeitos/música (avaliar) | sugestão |
| Apresentador em vídeo | HeyGen (chave em `API\`) | fase 2, só abertura, roteiro nosso |
| Estudo de referências | `scripts/analisar_referencia.py` (arquivos locais) | novo |
| Aprendizado contínuo | `feedback.py` (notas do dono por vídeo) | ativo |

## 7. Rotina semanal do CMO
1. Ler as notas da semana (`feedback.py summary`) e os 3 melhores/piores vídeos.
2. Rodar `analisar_referencia.py` em 2–3 referências novas e registrar aqui o que muda.
3. Propor ao CEO 1–3 ajustes (um por vez, para medir).
4. Atualizar este playbook.

## 8. Referências do dono
Os 6 vídeos indicados em 2026-10-05 ainda precisam ser analisados: o ambiente do Claude na nuvem não acessa o YouTube. Caminho: o dono salva os arquivos .mp4 (uso pessoal, estudo) e roda `analisar_referencia.py`; o Claude estuda a prancha + métricas e registra aqui o padrão (ritmo, gancho, tipos de texto, som).
