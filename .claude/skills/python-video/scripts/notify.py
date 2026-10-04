"""Aviso ao terminar a rotina diária (opcional). Nunca derruba a rotina: se o aviso falhar, só registra no log.

Canais (configure por variável de ambiente; sem configurar = só grava logs/ultimo-resumo.txt):

  Telegram (grátis, o mais simples)
    TELEGRAM_BOT_TOKEN   token do bot (crie falando com @BotFather)
    TELEGRAM_CHAT_ID     seu chat id (fale com o bot e abra https://api.telegram.org/bot<TOKEN>/getUpdates)

  E-mail (SMTP; no Gmail use uma "senha de app")
    ALNA_SMTP_HOST (ex.: smtp.gmail.com)  ALNA_SMTP_PORT (587)  ALNA_SMTP_USER  ALNA_SMTP_PASSWORD  ALNA_NOTIFY_TO

  python notify.py test     # envia uma mensagem de teste pelos canais configurados
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

from common import Logger, logs_dir


def format_summary(summary: dict) -> tuple[str, str]:
    """(assunto, corpo) em português, curto o bastante para o celular."""
    ready, target = summary.get("ready", 0), summary.get("target", 3)
    ok = ready >= target
    icon = "✅" if ok else ("⚠️" if ready else "❌")
    subj = f"{icon} ALNA vídeos {summary['day']}: {ready}/{target} prontos"
    lines = [subj, ""]
    for v in summary.get("videos", []):
        lines.append(f"• {v['produto']} — {v['arquetipo']}")
        if v.get("arquivo"):
            lines.append(f"  {v['arquivo']}")
    if summary.get("late"):
        lines.append("\n⏰ Rodou depois das 08:00 (o PC estava desligado ou a loja demorou).")
    for s in summary.get("skipped", []):
        lines.append(f"\n⚠️ Não produzido: {s.get('produto') or 'vídeo ' + str(s.get('slot', '?'))} — {s['motivo']}")
    errs = [e for e in summary.get("errors", [])]
    if errs:
        lines.append(f"\nTentativas que falharam e foram refeitas/puladas: {len(errs)}")
        for e in errs[:3]:
            lines.append(f"  - {(e if isinstance(e, str) else e.get('erro', ''))[:140]}")
    if not ok:
        lines.append("\nDetalhes: logs/daily-" + summary["day"] + ".json")
    return subj, "\n".join(lines)


def _send_telegram(text: str) -> bool:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return False
    import requests
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[:3900]}, timeout=20)
    r.raise_for_status()
    return True


def _send_email(subject: str, body: str) -> bool:
    host, user, pwd, to = (os.environ.get(k) for k in ("ALNA_SMTP_HOST", "ALNA_SMTP_USER", "ALNA_SMTP_PASSWORD", "ALNA_NOTIFY_TO"))
    if not (host and user and pwd):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to or user
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("ALNA_SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    return True


def notify_daily(summary: dict, log: Logger | None = None) -> dict:
    """Grava o resumo em arquivo e envia pelos canais configurados. Retorna {canal: True/False/erro}."""
    log = log or Logger("notify", echo=False)
    subj, body = format_summary(summary)
    result: dict = {}
    try:
        (logs_dir() / "ultimo-resumo.txt").write_text(body, encoding="utf-8")
        result["arquivo"] = True
    except Exception as e:  # pragma: no cover
        result["arquivo"] = str(e)[:100]
    for name, fn in (("telegram", lambda: _send_telegram(body)), ("email", lambda: _send_email(subj, body))):
        try:
            result[name] = fn()
        except Exception as e:
            result[name] = f"erro: {str(e)[:120]}"
            log.warn("aviso não enviado", canal=name, erro=str(e)[:160])
    log.info("aviso", **{k: v for k, v in result.items()})
    return result


def main(argv=None) -> int:
    if (argv or sys.argv[1:2]) != ["test"]:
        print(__doc__)
        return 0
    res = notify_daily({"day": "teste", "ready": 3, "target": 3, "videos": [
        {"produto": "Mensagem de teste do python-video", "arquetipo": "TESTE", "arquivo": None}]})
    print(res)
    return 0 if any(v is True for k, v in res.items() if k != "arquivo") else 1


if __name__ == "__main__":
    sys.exit(main())
