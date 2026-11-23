"""Доп. задание 2: e-mail оповещение о результате работы скрипта."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger("mailer")


def send_report(subject: str, body: str, log_file: Optional[Path] = None) -> None:
    if not (config.EMAIL_SENDER and config.EMAIL_PASSWORD and config.EMAIL_RECIPIENTS):
        log.warning("Почта не настроена (EMAIL_SENDER / EMAIL_PASSWORD / EMAIL_RECIPIENTS) — письмо не отправлено")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = ", ".join(config.EMAIL_RECIPIENTS)
    msg.set_content(body)

    if log_file and config.EMAIL_ATTACH_LOG and log_file.exists():
        msg.add_attachment(log_file.read_bytes(), maintype="text", subtype="plain",
                           filename=log_file.name)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, context=context) as server:
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.send_message(msg)
    log.info("Письмо отправлено: %s", ", ".join(config.EMAIL_RECIPIENTS))
