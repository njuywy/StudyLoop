import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = ("https://njuywy.github.io",)
    pages_url: str = "https://njuywy.github.io/StudyLoop/"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls_mode: str = "starttls"
    smtp_username: str = field(default="", repr=False)
    smtp_password: str = field(default="", repr=False)
    smtp_from: str = field(default="", repr=False)
    smtp_timeout: float = 5
    register_limit: int = 10
    resend_limit: int = 20
    login_limit: int = 10
    password_reset_limit: int = 10

    def __post_init__(self):
        if self.smtp_tls_mode not in {"starttls", "ssl"}:
            raise ValueError("SMTP_TLS_MODE must be starttls or ssl")
        if not 1 <= self.smtp_port <= 65535 or not 0 < self.smtp_timeout <= 10:
            raise ValueError("Invalid SMTP port or timeout (maximum 10 seconds)")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        if any(c in self.smtp_from for c in "\r\n"):
            raise ValueError("Invalid SMTP_FROM")
        if (
            min(self.register_limit, self.resend_limit, self.login_limit, self.password_reset_limit)
            < 1
        ):
            raise ValueError("Entry rate limits must be positive")
        parsed = urlsplit(self.pages_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("PAGES_URL must be an HTTPS base URL without query or fragment")
        if not self.pages_url.endswith("/"):
            raise ValueError("PAGES_URL must end in /")

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.environ.get("CORS_ORIGINS", "https://njuywy.github.io").split(",")
            if origin.strip()
        )
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or "*" in parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain exact HTTP(S) origins without paths")
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            cors_origins=origins,
            pages_url=os.environ.get("PAGES_URL", "https://njuywy.github.io/StudyLoop/"),
            smtp_host=os.environ.get("SMTP_HOST", ""),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_tls_mode=os.environ.get("SMTP_TLS_MODE", "starttls"),
            smtp_username=os.environ.get("SMTP_USERNAME", ""),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            smtp_from=os.environ.get("SMTP_FROM", ""),
            smtp_timeout=float(os.environ.get("SMTP_TIMEOUT", "5")),
            register_limit=int(os.environ.get("REGISTER_LIMIT", "10")),
            resend_limit=int(os.environ.get("RESEND_LIMIT", "20")),
            login_limit=int(os.environ.get("LOGIN_LIMIT", "10")),
            password_reset_limit=int(os.environ.get("PASSWORD_RESET_LIMIT", "10")),
        )
