from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from ..entries.requests_entry import RequestsResponseTraceEntry
from ..entries.trace_entry import TraceEntry


def entry_to_exchange(entry: TraceEntry) -> Dict:
    """Convert a TraceEntry to an exchange dictionary for multifile format.

    Args:
        entry: The TraceEntry to convert

    Returns:
        Dictionary representing the exchange in multifile format
    """
    # Get timestamp from timeline if available, otherwise use current time
    timestamp = datetime.now(timezone.utc)
    if entry.timeline.response_end:
        timestamp = entry.timeline.response_end
    elif entry.timeline.request_start:
        timestamp = entry.timeline.request_start

    # Get elapsed time
    elapsed_ms = 0
    if entry.timeline.request_start and entry.timeline.response_end:
        delta = entry.timeline.response_end - entry.timeline.request_start
        elapsed_ms = int(delta.total_seconds() * 1000)
    elif isinstance(entry, RequestsResponseTraceEntry):
        elapsed_ms = entry.elapsed_ms

    # Get reason phrase if available (from RequestsResponseTraceEntry)
    reason = None
    if isinstance(entry, RequestsResponseTraceEntry):
        reason = entry.reason

    exchange = {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "request": {
            "url": str(entry.request.url),
            "headers": entry.request.headers,
        },
        "response": {
            "status_code": entry.response.status_code,
            "reason": reason,
            "headers": entry.response.headers,
        },
        "elapsed_ms": elapsed_ms,
    }
    return exchange


def write_multifile_entry(
    folder: str,
    index: int,
    entry: TraceEntry,
    body_bytes: Optional[bytes] = None,
    body_extension: Optional[str] = None,
) -> None:
    """Write meta, body and annotation files for a TraceEntry into `folder` using index.

    Files written:
    - request_{index}.meta.json
    - request_{index}.body{body_extension} (binary, e.g., .body.m3u8 or .body.mpd)
    - request_{index}.{name}.txt for each annotation

    Args:
        folder: Directory to write files to
        index: Request index number
        entry: TraceEntry object containing request/response data
        body_bytes: Optional body content as bytes (if not provided, extracted from entry)
        body_extension: Optional extension to append after .body (e.g., ".m3u8", ".mpd")
    """
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    basename = f"request_{index}"
    exchange = entry_to_exchange(entry)

    meta_path = folder_path / f"{basename}.meta.json"
    with meta_path.open("w", encoding="utf-8") as mf:
        json.dump(exchange, mf, indent=2)

    # Body
    # TODO: determine if from the entry (content-type) if not provided
    body_extension = body_extension or ""
    body_path = folder_path / f"{basename}.body{body_extension}"
    if body_bytes is None:
        # Extract body bytes from entry
        body = entry.response.body
        body_bytes = body._get_decoded_body()

    if body_bytes is not None:
        with body_path.open("wb") as bf:
            bf.write(body_bytes)

    # Annotations - write all annotations from entry
    for name, text in entry.annotations.items():
        ann_path = folder_path / f"{basename}.{name}.txt"
        try:
            with ann_path.open("w", encoding="utf-8") as af:
                af.write(text)
        except Exception:
            pass
