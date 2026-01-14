from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from ..entries.requests_entry import RequestsResponseTraceEntry
from ..entries.trace_entry import TraceEntry
from ..utils.formats import get_extension_for_entry


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


class MultifileWriter:
    """Writer for multifile trace format.

    Writes trace entries to a folder with the following structure:
    - request_{index:06d}.meta.json
    - request_{index:06d}.body{extension}
    - request_{index:06d}.{annotation_name}.txt
    """

    def __init__(self, folder: str | Path):
        """Initialize the MultifileWriter.

        Args:
            folder: Path to the folder where files will be written
        """
        self.folder_path = Path(folder)
        self.folder_path.mkdir(parents=True, exist_ok=True)

    def add_entry(
        self,
        entry: TraceEntry,
        index: int,
        body_bytes: Optional[bytes] = None,
    ) -> None:
        """Add a trace entry to the multifile archive.

        Files written:
        - request_{index:06d}.meta.json
        - request_{index:06d}.body{extension} (extension determined from content-type)
        - request_{index:06d}.{name}.txt for each annotation

        Args:
            entry: TraceEntry object to write
            index: Request index number (will be zero-padded to 6 digits)
            body_bytes: Optional body content as bytes (if not provided, extracted from entry)
        """
        # Format index with zero-padding to 6 digits
        index_str = f"{index:06d}"
        basename = f"request_{index_str}"
        exchange = entry_to_exchange(entry)

        # Write meta.json
        meta_path = self.folder_path / f"{basename}.meta.json"
        with meta_path.open("w", encoding="utf-8") as mf:
            json.dump(exchange, mf, indent=2)

        # Determine extension from content-type or URL
        extension = get_extension_for_entry(entry)

        # Write body file
        if body_bytes is None:
            # Extract body bytes from entry
            body = entry.response.body
            body_bytes = body._get_decoded_body()

        if body_bytes is not None:
            body_path = self.folder_path / f"{basename}.body{extension}"
            with body_path.open("wb") as bf:
                bf.write(body_bytes)

        # Write annotations
        for name, text in entry.annotations.items():
            ann_path = self.folder_path / f"{basename}.{name}.txt"
            try:
                with ann_path.open("w", encoding="utf-8") as af:
                    af.write(text)
            except Exception:
                pass
