import io
import logging
import os
import re
import warnings
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError

from studyloop.registration import AuthError, connect
from studyloop.sessions import current_user, lock_current_user

router = APIRouter(prefix="/api/v1/me/avatar")
MAX_BYTES = 2_097_152
MAX_PIXELS = 16_000_000
FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}
KEY = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")
logger = logging.getLogger(__name__)


def validate_image(data: bytes, content_type: str | None) -> str:
    if not data or len(data) > MAX_BYTES:
        raise AuthError(413, "AVATAR_TOO_LARGE", "头像不能为空，且不能超过 2 MiB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=list(FORMATS)) as picture:
                extension, mime = FORMATS[picture.format]
                if content_type != mime:
                    raise ValueError("Mismatched image format")
                if picture.width * picture.height > MAX_PIXELS:
                    raise ValueError("Too many pixels")
                picture.verify()
            # verify() alone does not decode pixels. Bound both frame count and total pixels.
            with Image.open(io.BytesIO(data), formats=list(FORMATS)) as picture:
                frames = getattr(picture, "n_frames", 1)
                if frames > 32 or picture.width * picture.height * frames > MAX_PIXELS:
                    raise ValueError("Too many decoded pixels")
                for frame in range(frames):
                    picture.seek(frame)
                    picture.load()
        return extension
    except (
        ValueError,
        OSError,
        EOFError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AuthError(
            422, "INVALID_AVATAR", "请选择可解码的 JPEG、PNG 或 WebP，累计像素不超过 1600 万。"
        ) from None


def image_response(data: bytes, key: str):
    mime = next(mime for extension, mime in FORMATS.values() if key.endswith("." + extension))
    return Response(
        data,
        media_type=mime,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def cleanup_unreferenced(settings, user_id):
    """Re-read under the account lock, including after an ambiguous commit failure.

    No writer can create a candidate while this lock is held. Never remove the
    current reference; unavailable storage/DB leaves cleanup for the next upload.
    """
    try:
        with connect(settings) as connection:
            row = connection.execute(
                "SELECT avatar_key FROM users WHERE id = %s FOR UPDATE", (user_id,)
            ).fetchone()
            directory = Path(settings.avatar_directory) / str(user_id)
            if row and directory.exists():
                for path in directory.iterdir():
                    if KEY.fullmatch(path.name) and path.name != row["avatar_key"]:
                        path.unlink(missing_ok=True)
    except (OSError, psycopg.Error):
        # Do not log paths, credentials, driver messages or user input.
        logger.warning("Avatar cleanup deferred; retry on next upload")


@router.get("")
def read_avatar(request: Request, user: Annotated[dict, Depends(current_user)]):
    try:
        with connect(request.app.state.settings) as connection:
            locked = lock_current_user(connection, user)
            key = locked["avatar_key"]
            if not key:
                raise AuthError(404, "NO_AVATAR", "尚未上传头像。")
            # Read while holding the lock, so replacement cleanup cannot unlink first.
            data = (
                Path(request.app.state.settings.avatar_directory) / str(user["id"]) / key
            ).read_bytes()
        return image_response(data, key)
    except OSError:
        raise AuthError(503, "AVATAR_UNAVAILABLE", "头像暂不可用，请稍后重试。") from None


@router.put("")
def replace_avatar(
    request: Request, file: UploadFile, user: Annotated[dict, Depends(current_user)]
):
    data = file.file.read(MAX_BYTES + 1)
    extension = validate_image(data, file.content_type)
    settings = request.app.state.settings
    key = uuid4().hex + "." + extension
    directory = Path(settings.avatar_directory) / str(user["id"])
    try:
        with connect(settings) as connection:
            lock_current_user(connection, user)
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Immutable candidate is fully written before its reference can commit.
            with (directory / key).open("xb") as output:
                os.chmod(directory / key, 0o600)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            connection.execute("UPDATE users SET avatar_key = %s WHERE id = %s", (key, user["id"]))
    except OSError:
        raise AuthError(503, "AVATAR_UNAVAILABLE", "头像保存失败，请稍后重试。") from None
    finally:
        # Also handles partial files and rolled-back references. A commit whose
        # result was lost is resolved from DB before deleting any candidate.
        cleanup_unreferenced(settings, user["id"])
    return image_response(data, key)
