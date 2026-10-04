import smtplib

import pytest

from studyloop import mail
from studyloop.mail import MailUnavailable, send_verification
from studyloop.settings import Settings


@pytest.mark.parametrize("mode", ["ssl", "starttls"])
def test_smtp_uses_tls_auth_timeout_and_real_message(monkeypatch, mode):
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
    link = "https://njuywy.github.io/StudyLoop/#/verify-email?token=test"
    send_verification(settings, "recipient@example.com", link)
    assert calls[0][3]["timeout"] == 5
    assert ("login", "sender", "private") in calls
    message = next(c[1] for c in calls if c[0] == "message")
    assert message["To"] == "recipient@example.com" and link in message.get_content()
    assert any(c[0] == "tls" for c in calls) == (mode == "starttls")
    context = (
        calls[0][3]["context"]
        if mode == "ssl"
        else next(c[1]["context"] for c in calls if c[0] == "tls")
    )
    assert context.check_hostname
    assert calls[-1] == ("close",)


@pytest.mark.parametrize("error", [TimeoutError, smtplib.SMTPAuthenticationError])
def test_mail_errors_are_redacted(monkeypatch, error):
    def fail(*args, **kwargs):
        if error is TimeoutError:
            raise TimeoutError("private mail details")
        raise smtplib.SMTPAuthenticationError(535, b"private credentials")

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", fail)
    with pytest.raises(MailUnavailable) as caught:
        send_verification(
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


@pytest.mark.parametrize("mode", ["ssl", "starttls"])
def test_ineligible_address_checks_transport_without_sending_mail(monkeypatch, mode):
    calls = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            self.greeted = False

        def starttls(self, **kwargs):
            calls.append("tls")
            self.greeted = False

        def ehlo_or_helo_if_needed(self):
            self.greeted = True
            calls.append("greeting")

        def mail(self, sender):
            assert self.greeted, "The server requires EHLO after TLS before MAIL"
            calls.append("mail")
            return 250, b"ok"

        def rcpt(self, recipient):
            calls.append("rcpt")
            return 250, b"ok"

        def rset(self):
            calls.append("reset")
            return 250, b"ok"

        def close(self):
            calls.append("close")

        def send_message(self, message):
            pytest.fail("No message should be sent for an ineligible account")

    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", SMTP)
    send_verification(
        Settings(smtp_host="smtp.example.com", smtp_from="sender@example.com", smtp_tls_mode=mode),
        "recipient@example.com",
        None,
    )
    assert calls == (["tls"] if mode == "starttls" else []) + [
        "greeting",
        "mail",
        "rcpt",
        "reset",
        "close",
    ]
