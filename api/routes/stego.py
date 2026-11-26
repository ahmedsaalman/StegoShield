"""Hide a message in an image, and reveal it again."""

from __future__ import annotations

import base64
from collections.abc import Callable
from functools import partial
from typing import Annotated

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import x25519
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from PIL import Image

from api.config import Settings
from api.dependencies import get_settings, run_cpu_bound
from api.errors import ApiError
from api.images import download_filename, encode_png, load_cover_image, load_stego_image
from api.routes.keys import parse_public_key
from api.schemas import (
    EmbeddingAlgorithmChoice,
    EmbeddingLayoutChoice,
    KeyMethod,
    MessageEncoding,
    RevealResponse,
)
from core.keys import import_private_key_pem
from core.pipeline import (
    stego_decode_asymmetric,
    stego_decode_password,
    stego_encode_asymmetric,
    stego_encode_password,
)

MAX_SECRET_FIELD_CHARS = 1024
MAX_KEY_FIELD_CHARS = 8192
INVALID_PRIVATE_KEY_MESSAGE = (
    "Couldn't read the private key. Check that you chose the right .pem file and, "
    "if it is protected, that the passphrase is correct."
)

router = APIRouter(prefix="/api", tags=["steganography"])

Encoder = Callable[[Image.Image, bytes], Image.Image]
Decoder = Callable[[Image.Image], bytes]


@router.post(
    "/hide",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "The image with the message hidden in it."}},
)
async def hide_message(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    cover: Annotated[UploadFile, File(description="Image to hide the message in.")],
    message: Annotated[str, Form(min_length=1)],
    method: Annotated[KeyMethod, Form()],
    password: Annotated[str | None, Form(max_length=MAX_SECRET_FIELD_CHARS)] = None,
    recipient_public_key: Annotated[str | None, Form(max_length=MAX_KEY_FIELD_CHARS)] = None,
    algorithm: Annotated[EmbeddingAlgorithmChoice, Form()] = EmbeddingAlgorithmChoice.MATCHING,
    layout: Annotated[EmbeddingLayoutChoice, Form()] = EmbeddingLayoutChoice.PSEUDORANDOM,
) -> Response:
    """Encrypt the message and hide it in the cover. Returns a PNG; nothing is stored."""
    message_bytes = _encode_message(message, settings.max_message_bytes)
    encoder = _build_encoder(method, password, recipient_public_key, algorithm, layout)
    uploaded = await load_cover_image(cover, settings)
    stego_image = await run_cpu_bound(request, encoder, uploaded.image, message_bytes)
    png_bytes = await run_cpu_bound(request, encode_png, stego_image)
    filename = download_filename(uploaded.filename)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/reveal", response_model=RevealResponse)
async def reveal_message(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    image: Annotated[UploadFile, File(description="PNG that may contain a hidden message.")],
    method: Annotated[KeyMethod, Form()],
    password: Annotated[str | None, Form(max_length=MAX_SECRET_FIELD_CHARS)] = None,
    private_key: Annotated[str | None, Form(max_length=MAX_KEY_FIELD_CHARS)] = None,
    passphrase: Annotated[str | None, Form(max_length=MAX_SECRET_FIELD_CHARS)] = None,
    layout: Annotated[EmbeddingLayoutChoice, Form()] = EmbeddingLayoutChoice.PSEUDORANDOM,
) -> RevealResponse:
    """Find, verify and decrypt a hidden message. Fails closed on a wrong key or a modified image."""
    decoder = _build_decoder(method, password, private_key, passphrase, layout)
    uploaded = await load_stego_image(image, settings)
    plaintext = await run_cpu_bound(request, decoder, uploaded.image)
    return _to_reveal_response(plaintext)


def _encode_message(message: str, max_message_bytes: int) -> bytes:
    encoded = message.encode("utf-8")
    if len(encoded) > max_message_bytes:
        raise ApiError(
            413,
            "message_too_long",
            f"The message is {len(encoded):,} bytes; the limit is {max_message_bytes:,} bytes.",
            field="message",
        )
    return encoded


def _build_encoder(
    method: KeyMethod,
    password: str | None,
    recipient_public_key: str | None,
    algorithm: EmbeddingAlgorithmChoice,
    layout: EmbeddingLayoutChoice,
) -> Encoder:
    options = {"algorithm": algorithm.value, "mode": layout.value}
    if method is KeyMethod.PASSWORD:
        secret = _require(password, "password", "Enter a password to protect the message.")
        return lambda cover, message: stego_encode_password(cover, message, secret, **options)
    key_text = _require(recipient_public_key, "recipient_public_key", "Add the recipient's public key.")
    public_key = parse_public_key(key_text, field="recipient_public_key")
    return lambda cover, message: stego_encode_asymmetric(cover, message, public_key, **options)


def _build_decoder(
    method: KeyMethod,
    password: str | None,
    private_key: str | None,
    passphrase: str | None,
    layout: EmbeddingLayoutChoice,
) -> Decoder:
    if method is KeyMethod.PASSWORD:
        secret = _require(password, "password", "Enter the password the message was protected with.")
        return partial(_decode_with_password, password=secret, layout=layout)
    key_text = _require(private_key, "private_key", "Add your private key (.pem file).")
    key = _parse_private_key(key_text, passphrase or None)
    return partial(_decode_with_private_key, private_key=key, layout=layout)


def _decode_with_password(stego: Image.Image, password: str, layout: EmbeddingLayoutChoice) -> bytes:
    return stego_decode_password(stego, password, mode=layout.value)


def _decode_with_private_key(
    stego: Image.Image, private_key: x25519.X25519PrivateKey, layout: EmbeddingLayoutChoice
) -> bytes:
    return stego_decode_asymmetric(stego, private_key, mode=layout.value)


def _parse_private_key(pem_text: str, passphrase: str | None) -> x25519.X25519PrivateKey:
    try:
        return import_private_key_pem(pem_text, password=passphrase)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise ApiError(422, "invalid_key", INVALID_PRIVATE_KEY_MESSAGE, field="private_key") from exc


def _require(value: str | None, field: str, message: str) -> str:
    if not value:
        raise ApiError(422, "validation_error", message, field=field)
    return value


def _to_reveal_response(plaintext: bytes) -> RevealResponse:
    try:
        text, encoding = plaintext.decode("utf-8"), MessageEncoding.UTF8
    except UnicodeDecodeError:
        text, encoding = base64.b64encode(plaintext).decode("ascii"), MessageEncoding.BASE64
    return RevealResponse(message=text, encoding=encoding, message_bytes=len(plaintext))
