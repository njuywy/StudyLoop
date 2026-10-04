import smtplib
import ssl
from email.message import EmailMessage

from studyloop.settings import Settings


class MailUnavailable(Exception):
    """Safe boundary: never expose transport errors, recipients or credentials."""


def send_verification(settings: Settings, recipient: str, link: str | None) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise MailUnavailable()
    smtp = None
    try:
        context = ssl.create_default_context()
        if settings.smtp_tls_mode == "ssl":
            smtp = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
                context=context,
            )
        else:
            smtp = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
            )
            smtp.starttls(context=context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        if link is None:
            # Same TLS/auth/envelope checks for absent or ineligible accounts, without sending.
            # RSET discards the envelope; no DATA command or email is issued.
            smtp.ehlo_or_helo_if_needed()
            if smtp.mail(settings.smtp_from)[0] != 250 or smtp.rcpt(recipient)[0] not in {250, 251}:
                raise MailUnavailable()
            if smtp.rset()[0] != 250:
                raise MailUnavailable()
        else:
            message = EmailMessage()
            message["Subject"] = "验证你的 StudyLoop 邮箱"
            message["From"] = settings.smtp_from
            message["To"] = recipient
            message.set_content(
                "欢迎来到 StudyLoop！\n\n请在 24 小时内打开以下链接并确认验证邮箱：\n"
                f"{link}\n\n链接仅可使用一次。如果你没有注册，请忽略此邮件。"
            )
            if smtp.send_message(message):
                raise MailUnavailable()
    except (OSError, smtplib.SMTPException, ValueError):
        raise MailUnavailable() from None
    finally:
        # QUIT failure after DATA was accepted must not invalidate a delivered link.
        if smtp is not None:
            try:
                smtp.close()
            except OSError:
                pass
