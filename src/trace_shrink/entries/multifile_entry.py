from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from yarl import URL

from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)


class MultiFileTraceEntry(TraceEntry):
    """TraceEntry backed by a set of files produced by OutputStore.

    Expects a meta JSON dict like the one OutputStore writes, a body bytes
    object (or None), and optional annotations dict.
    """

    def __init__(
        self,
        index: int,
        exchange: Dict[str, Any],
        body_bytes: Optional[bytes],
        annotations: Optional[Dict[str, str]] = None,
    ):
        self._exchange = exchange
        self._body_bytes = body_bytes
        annotations_dict = annotations or {}

        comment = exchange.get("comment")
        highlight = exchange.get("highlight")

        # Parse request
        request_data = exchange.get("request", {})
        try:
            url = URL(request_data.get("url", ""))
        except Exception:
            url = URL("")

        request = RequestDetails(
            url=url,
            method=request_data.get("method", "GET").upper(),
            headers=dict(request_data.get("headers", {})),
        )

        # Parse response
        response_data = exchange.get("response", {})
        response_headers = dict(response_data.get("headers", {}))

        body_text = None
        if body_bytes is not None:
            try:
                body_text = body_bytes.decode("utf-8", errors="replace")
            except Exception:
                body_text = None

        body_size = len(body_bytes) if body_bytes is not None else 0

        response_body = ResponseBodyDetails(
            text=body_text,
            raw_size=body_size,
            compressed_size=body_size,
            decoded_body=body_bytes,
        )

        # Extract content_type from response headers (Content-Type header)
        # Fall back to response_data if not in headers
        content_type = response_data.get("content_type")
        if not content_type:
            content_type = response_headers.get("Content-Type")

        # Extract mime_type from content_type (split on ';' to remove parameters)
        # Fall back to response_data if not available
        mime_type = response_data.get("mime_type")
        if not mime_type and content_type:
            mime_type = (
                content_type.split(";")[0].strip()
                if isinstance(content_type, str)
                else None
            )

        response = ResponseDetails(
            headers=response_headers,
            status_code=int(response_data.get("status_code", 0)),
            mime_type=mime_type,
            content_type=content_type,
            body=response_body,
        )

        # Parse timeline
        timestamp_str = exchange.get("timestamp")
        elapsed_ms = exchange.get("elapsed_ms")

        request_start = None
        if timestamp_str:
            try:
                request_start = datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                )
            except Exception:
                request_start = None

        response_end = None
        if request_start and elapsed_ms:
            try:
                response_end = request_start + timedelta(milliseconds=elapsed_ms)
            except Exception:
                response_end = None

        timeline = TimelineDetails(
            request_start=request_start,
            request_end=None,
            response_start=None,
            response_end=response_end,
        )

        # Initialize TraceEntry
        # Filter out comment and highlight from annotations dict (handled separately)
        filtered_annotations = {
            k: v
            for k, v in annotations_dict.items()
            if k not in ("comment", "highlight")
        }
        super().__init__(
            index=index,
            entry_id=str(index),
            request=request,
            response=response,
            timeline=timeline,
            comment=comment,
            highlight=highlight,
            annotations=filtered_annotations,
        )

    @classmethod
    def from_files(
        cls,
        index: int,
        meta_path: str,
        body_path: str,
        annotations_paths: Optional[List[str]] = None,
    ):
        # Read meta
        with open(meta_path, "r") as f:
            exchange = json.load(f)

        # Read body
        body_bytes = None
        try:
            with open(body_path, "rb") as bf:
                body_bytes = bf.read()
        except Exception:
            body_bytes = None

        # Read annotations
        ann: Dict[str, str] = {}
        if annotations_paths:
            for p in annotations_paths:
                try:
                    ann_path = Path(p)
                    with ann_path.open("r") as af:
                        basename = ann_path.name
                        # Extract annotation name from both padded and unpadded filenames.
                        # e.g., request_1.digest.txt -> digest
                        # e.g., request_000001.digest.txt -> digest
                        m = re.match(r"^request_\d+\.(.+)\.txt$", basename)
                        ann_name = m.group(1) if m else basename.replace(".txt", "")
                        ann[ann_name] = af.read()
                except Exception:
                    pass

        return cls(index, exchange, body_bytes, ann)
