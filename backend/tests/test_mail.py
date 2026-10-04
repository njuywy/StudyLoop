import smtplib

import pytest

from studyloop import mail
from studyloop.mail import MailUnavailable, send_password_reset, send_verification
from studyloop.settings import Settings


@pytest.mark.parametrize("mode", ["ssl", "starttls"])
@pytest.mark.parametrize(
    "sender,path,duration",
    [
        (send_verification, "verify-email", "24 小时"),
        (send_password_reset, "reset-password", "30 分钟"),
    ],
)
def test_smtp_uses_tls_auth_timeout_and_real_message(monkeypatch, mode, sender, path, duration):
    calls = []

    class SMTP:
        def __init__(self, host, port, **kwargs):
            calls.append(("connect", host, port, kwargs))

        def starttls(self, **kwargs):
            calls.append(("tls", kwargs))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("message", message))
            return {}

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", SMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_from="sender@example.com",
        smtp_username="sender",
        smtp_password="private",
        smtp_tls_mode=mode,
    )
    link = f"https://njuywy.github.io/StudyLoop/#/{path}?token=test"
    sender(settings, "recipient@example.com", link)
    assert calls[0][3]["timeout"] == 5
    assert ("login", "sender", "private") in calls
    message = next(c[1] for c in calls if c[0] == "message")
    assert message["To"] == "recipient@example.com" and link in message.get_content()
    assert duration in message.get_content()
    assert any(c[0] == "tls" for c in calls) == (mode == "starttls")
    context = (
        calls[0][3]["context"]
        if mode == "ssl"
        else next(c[1]["context"] for c in calls if c[0] == "tls")
    )
    assert context.check_hostname
    assert calls[-1] == ("close",)


@pytest.mark.parametrize("error", [TimeoutError, smtplib.SMTPAuthenticationError])
@pytest.mark.parametrize("sender", [send_verification, send_password_reset])
def test_mail_errors_are_redacted(monkeypatch, error, sender):
    def fail(*args, **kwargs):
        if error is TimeoutError:
            raise TimeoutError("private mail details")
        raise smtplib.SMTPAuthenticationError(535, b"private credentials")

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", fail)
    with pytest.raises(MailUnavailable) as caught:
        sender(
            Settings(
                smtp_host="smtp.example.com", smtp_from="sender@example.com", smtp_tls_mode="ssl"
            ),
            "recipient@example.com",
            "https://example.com/#/verify-email?token=secret",
        )
    assert str(caught.value) == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"smtp_tls_mode": "none"},
        {"smtp_timeout": 0},
        {"smtp_timeout": 11},
        {"smtp_port": 0},
        {"smtp_username": "incomplete"},
        {"pages_url": "http://example.com/"},
        {"pages_url": "https://example.com/#/bad"},
        {"smtp_from": "header\ninjection"},
        {"register_limit": 0},
    ],
)
def test_invalid_configuration_fails_closed(changes):
    with pytest.raises(ValueError):
        Settings(**changes)


def test_smtp_data_failure_is_a_safe_transport_error(monkeypatch):
    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def send_message(self, message):
            raise smtplib.SMTPDataError(451, b"internal mail detail")

        def close(self):
            pass

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", SMTP)
    with pytest.raises(MailUnavailable) as caught:
        send_verification(
            Settings(
                smtp_host="smtp.example.com", smtp_from="sender@example.com", smtp_tls_mode="ssl"
            ),
            "recipient@example.com",
            "https://example.com/#/verify-email?token=secret",
        )
    assert str(caught.value) == ""
