# python-video — contexto para sessões do Claude no computador do dono

Leia `SKILL.md` antes de qualquer coisa. Resumo das regras combinadas:

* **Sócio, não executor:** avalie se cada pedido ajuda ou quebra a skill; traga sugestões; o dono aprova.
* **Nunca inventar característica de produto.** Só fato confirmado (loja, `config/user_confirmed.json` ou dono por escrito). Vídeo final sempre H.264/AAC, 9:16 1080x1920, 30 fps, 15–18 s.
* **Objetivo de cada vídeo:** conexão, credibilidade e confiança, com UMA chamada para ação (arquétipo `CONNECT_TRUST` / `DEMO_MIX`). Texto curto de relance (gancho ≤ 7 palavras, CTA ≤ 5).
* **Crianças nos clipes:** só no `--demo`, só com fato de uso confirmado que fale de crianças, nunca em close, sempre "Imagem ilustrativa"; texto fala com o adulto. Rotina diária: nunca.
* **Chaves:** ficam em `API\` (ou `APIpixabay`) neste computador. Nunca no repositório, no chat, em log ou em ZIP. Se uma chave foi exposta, recomende trocar.
* **Dados reais rodam aqui (Windows):** loja, Pixabay, Drive `G:`, vídeos. Teste com `.venv\Scripts\python.exe`.
* **Pipeline principal Higgsfield (`persona/`, `platforms/`) não se altera sem necessidade.** Esta skill é independente e sem IA generativa; HeyGen (fase 2, opcional) só com aprovação do dono: apenas apresentador na abertura, roteiro nosso, nunca Video Agent, nunca crianças geradas por IA.
* **Atualizações:** `scripts\atualizar.ps1` (git pull da branch `claude/youthful-faraday-q0o4b7` + cópia preservando o que é só seu).
