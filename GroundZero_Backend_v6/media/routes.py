"""Photo storage for GroundZero: journal photos and place pictures.

Files are stored on disk under ./media_store with random unguessable ids
and served back by id, so the Flutter app can show them with a normal
image URL. Only real images are accepted (checked by their magic bytes),
capped at 8 MB. Swap this module for S3/Cloud Storage in production; the
rest of the app only ever sees the returned URL.
"""
from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user
from auth.models import User

router = APIRouter(prefix="/media", tags=["media"])

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media_store"
MAX_BYTES = 8 * 1024 * 1024
_ID_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|mp4)$")


def _kind(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def strip_metadata(data: bytes, ext: str) -> bytes:
    """Re-encode so hidden EXIF (GPS position, camera, owner) never gets
    stored or served. Orientation is applied first so photos stay upright.
    A file that can't be decoded as an image is rejected."""
    from io import BytesIO
    try:
        from PIL import Image, ImageOps
        img = Image.open(BytesIO(data))
        img.load()
        img = ImageOps.exif_transpose(img)
        if img.width * img.height > 50_000_000:
            raise HTTPException(413, "That photo is too large.")
        out = BytesIO()
        if ext == "jpg":
            img.convert("RGB").save(out, "JPEG", quality=90)
        elif ext == "png":
            img.save(out, "PNG")
        else:
            img.save(out, "WEBP", quality=90)
        return out.getvalue()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(415, "That file isn't a valid photo.")


class UploadIn(BaseModel):
    data_base64: str = Field(min_length=100)


class UploadOut(BaseModel):
    url: str
    id: str


def public_base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def path_for_url(url: str) -> Path | None:
    m = re.search(r"/media/files/([0-9a-f]{32}\.(?:jpg|png|webp|mp4))$", url or "")
    if not m:
        return None
    p = MEDIA_DIR / m.group(1)
    return p if p.exists() else None


@router.post("/upload", response_model=UploadOut)
async def upload(body: UploadIn, request: Request, user: User = Depends(get_current_user)) -> UploadOut:
    raw = body.data_base64.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "That photo couldn't be read. Please try another.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That photo is too large (max 8 MB).")
    ext = _kind(data)
    if ext is None:
        raise HTTPException(415, "Only JPG, PNG or WebP photos are supported.")
    data = strip_metadata(data, ext)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (MEDIA_DIR / name).write_bytes(data)
    return UploadOut(url=f"{public_base(request)}/media/files/{name}", id=name)


@router.get("/files/{name}")
async def get_file(name: str):
    if not _ID_RE.match(name):
        raise HTTPException(404, "Not found")
    p = MEDIA_DIR / name
    if not p.exists():
        raise HTTPException(404, "Not found")
    mt = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "mp4": "video/mp4"}[name.rsplit(".", 1)[1]]
    return FileResponse(p, media_type=mt, headers={"Cache-Control": "public, max-age=86400"})
