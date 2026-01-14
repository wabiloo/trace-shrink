from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from requests import Response


def response_to_exchange(
    response: Response, facets: Dict[str, str] | None = None
) -> Dict:
    facets = facets or {}
    exchange = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": {
            "url": str(response.request.url),
            "headers": dict(response.request.headers),
        },
        "response": {
            "status_code": response.status_code,
            "reason": response.reason,
            "headers": dict(response.headers),
        },
        "facets": facets,
        "elapsed_ms": int(response.elapsed.total_seconds() * 1000)
        if hasattr(response, "elapsed")
        else 0,
    }
    return exchange


def write_multifile_entry(
    folder: str,
    index: int,
    response: Response,
    body_bytes: Optional[bytes] = None,
    annotations: Optional[Dict[str, str]] = None,
    facets: Optional[Dict[str, str]] = None,
    body_extension: Optional[str] = None,
) -> None:
    """Write meta, body and annotation files for a response into `folder` using index.

    Files written:
    - request_{index}.meta.json
    - request_{index}.body{body_extension} (binary, e.g., .body.m3u8 or .body.mpd)
    - request_{index}.{name}.txt for each annotation

    Args:
        folder: Directory to write files to
        index: Request index number
        response: HTTP response object
        body_bytes: Optional body content as bytes
        annotations: Optional dictionary of annotations to write as .txt files
        facets: Optional dictionary of facets to include in metadata
        body_extension: Optional extension to append after .body (e.g., ".m3u8", ".mpd")
    """
    os.makedirs(folder, exist_ok=True)
    basename = f"request_{index}"
    exchange = response_to_exchange(response, facets=facets)

    meta_path = os.path.join(folder, f"{basename}.meta.json")
    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump(exchange, mf, indent=2)

    # Body
    body_extension = body_extension or ""
    body_path = os.path.join(folder, f"{basename}.body{body_extension}")
    if body_bytes is None:
        try:
            # prefer raw bytes if available
            body_bytes = response.content
        except Exception:
            body_bytes = None

    if body_bytes is not None:
        with open(body_path, "wb") as bf:
            bf.write(body_bytes)

    # Annotations
    annotations = annotations or {}
    for name, text in annotations.items():
        ann_path = os.path.join(folder, f"{basename}.{name}.txt")
        try:
            with open(ann_path, "w", encoding="utf-8") as af:
                af.write(text)
        except Exception:
            pass
