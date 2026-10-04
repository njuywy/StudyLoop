import smtplib
import ssl
from email.message import EmailMessage

from studyloop.settings import Settings


class MailUnavailable(Exception):
    """Safe boundary: never expose transport errors, recipients or credentials."""


def send_verification(settings: Settings, recipient: str, link: str) -> None:
    send_message(
        settings,
        recipient,
        "验证你的 StudyLoop 邮箱",
        "欢迎来到 StudyLoop！\n\n请在 24 小时内打开以下链接并确认验证邮箱：\n"
        f"{link}\n\n链接仅可使用一次。如果你没有注册，请忽略此邮件。",
    )


def send_password_reset(settings: Settings, recipient: str, link: str) -> None:
    send_message(
        settings,
        recipient,
        "重置你的 StudyLoop 密码",
        "请在 30 分钟内打开以下链接，主动提交新密码：\n"
        f"{link}\n\n链接仅可使用一次。仅打开链接不会修改密码。"
        "如果你没有申请找回密码，请忽略此邮件。",
    )


def send_message(settings: Settings, recipient: str, subject: str, body: str) -> None:
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
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message.set_content(body)
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
