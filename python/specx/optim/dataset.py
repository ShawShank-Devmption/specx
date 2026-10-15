"""Export only gate-accepted training pairs with content-addressed PNG sidecars.

Screenshot paths are relative to dataset.jsonl for portable dataset relocation.
Missing images are null; raw screenshot payloads never enter the JSONL record.
"""

import hashlib
from typing import Any

from specx.client.io import append_jsonl
from specx.client.paths import stage_dir
from specx.client.schemas import validate
from specx.optim.bundles import FailureBundle
from specx.optim.images import decode_png, without_images


def export_accepted(bundles: list[FailureBundle], patch: dict[str, Any], arm: str) -> None:
    validate("patch", patch)
    if patch["modality"] != arm or any(
        bundle.split != "train"
        or bundle.trial_id not in patch["source_trial_ids"]
        or patch["tool_id"] not in bundle.tool_ids
        for bundle in bundles
    ):
        raise ValueError("Dataset requires matching train-only accepted evidence")
    # Validate all image transports before emitting any records.
    screenshots = [
        decode_png(bundle.screenshot_b64) if bundle.screenshot_b64 is not None else None
        for bundle in bundles
    ]
    directory = stage_dir("s4")
    for bundle, data in zip(bundles, screenshots, strict=True):
        screenshot_path = None
        if data is not None:
            screenshot_path = f"screenshots/{hashlib.sha256(data).hexdigest()}.png"
            path = directory / screenshot_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != data:
                raise ValueError("Screenshot content-address collision or corrupted existing image")
            if not path.exists():
                path.write_bytes(data)
        append_jsonl(
            directory / "dataset.jsonl",
            {
                "bundle_without_screenshot": without_images(bundle.model_dump()),
                "screenshot_path": screenshot_path,
                "accepted_patch": patch,
                "arm": arm,
            },
        )
