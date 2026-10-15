"""Validate screenshot transport and strip embedded images from text-only evidence."""

import base64
import binascii
from typing import Any


def decode_png(encoded: str) -> bytes:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Screenshot must be base64 PNG data") from error
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"):
        raise ValueError("Screenshot must contain a PNG header")
    return data


def without_images(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("type") == "image":
            return {"type": "text", "text": "[image omitted]"}
        return {
            key: without_images(item)
            for key, item in value.items()
            if key not in ("screenshot_b64", "final_screenshot_b64")
        }
    if isinstance(value, list):
        return [without_images(item) for item in value]
    return value
