import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = ("https://njuywy.github.io",)

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
        return cls(database_url=os.environ.get("DATABASE_URL", ""), cors_origins=origins)
