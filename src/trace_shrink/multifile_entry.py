from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from yarl import URL

from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)


class _MultiFileRequestDetails(RequestDetails):
    def __init__(self, request_data: Dict[str, Any]):
        self._data = request_data

    @property
    def url(self) -> URL:
        try:
            return URL(self._data.get("url", ""))
        except Exception:
            return URL("")

    @property
    def headers(self) -> Dict[str, str]:
        return dict(self._data.get("headers", {}))

    @property
    def method(self) -> str:
        return self._data.get("method", "GET").upper()


class _MultiFileResponseBodyDetails(ResponseBodyDetails):
    def __init__(self, body_content: Optional[bytes], raw_meta: Dict[str, Any]):
        self._body_content = body_content
        self._meta = raw_meta

    def _get_decoded_body(self) -> Optional[bytes]:
        return self._body_content

    @property
    def text(self) -> Optional[str]:
        if self._body_content is None:
            return None
        try:
            # try to decode as utf-8, fallback to replace
            return self._body_content.decode("utf-8", errors="replace")
        except Exception:
            return None

    @property
    def raw_size(self) -> Optional[int]:
        if self._body_content is None:
            return 0
        return len(self._body_content)

    @property
    def compressed_size(self) -> Optional[int]:
        # We don't have compressed info in folder format; use raw_size
        return self.raw_size


class _MultiFileResponseDetails(ResponseDetails):
    def __init__(self, response_data: Dict[str, Any], body_content: Optional[bytes], facets: Dict[str, Any]):
        self._data = response_data
        self._body = _MultiFileResponseBodyDetails(body_content, response_data)
        self._facets = facets

    @property
    def headers(self) -> Dict[str, str]:
        return dict(self._data.get("headers", {}))

    @property
    def mime_type(self) -> Optional[str]:
        return self._data.get("mime_type") or None

    @property
    def content_type(self) -> Optional[str]:
        return self._data.get("content_type") or None

    @property
    def body(self) -> ResponseBodyDetails:
        return self._body

    @property
    def status_code(self) -> int:
        return int(self._data.get("status_code", 0))


class _MultiFileTimelineDetails(TimelineDetails):
    def __init__(self, timestamp_str: Optional[str], elapsed_ms: Optional[int]):
        self._timestamp_str = timestamp_str
        self._elapsed_ms = elapsed_ms

    def _parse_ts(self) -> Optional[datetime]:
        if not self._timestamp_str:
            return None
        try:
            return datetime.fromisoformat(self._timestamp_str.replace("Z", "+00:00"))
        except Exception:
            return None

    @property
    def request_start(self) -> Optional[datetime]:
        return self._parse_ts()

    @property
    def request_end(self) -> Optional[datetime]:
        return None

    @property
    def response_start(self) -> Optional[datetime]:
        return None

    @property
    def response_end(self) -> Optional[datetime]:
        rs = self._parse_ts()
        if rs and self._elapsed_ms:
            try:
                return rs + timedelta(milliseconds=self._elapsed_ms)
            except Exception:
                return None
        return None


class MultiFileTraceEntry(TraceEntry):
    """TraceEntry backed by a set of files produced by OutputStore.

    Expects a meta JSON dict like the one OutputStore writes, a body bytes
    object (or None), and optional annotations dict.
    """

    def __init__(self, index: int, exchange: Dict[str, Any], body_bytes: Optional[bytes], annotations: Optional[Dict[str, str]] = None):
        self._index = index
        self._exchange = exchange
        self._body_bytes = body_bytes
        self._annotations = annotations or {}
        self._request = _MultiFileRequestDetails(self._exchange.get("request", {}))
        self._response = _MultiFileResponseDetails(self._exchange.get("response", {}), body_bytes, self._exchange.get("facets", {}))
        self._timeline = _MultiFileTimelineDetails(self._exchange.get("timestamp"), self._exchange.get("elapsed_ms"))

    @property
    def index(self) -> int:
        return self._index

    @property
    def id(self) -> str:
        return str(self._index)

    @property
    def request(self) -> RequestDetails:
        return self._request

    @property
    def response(self) -> ResponseDetails:
        return self._response

    @property
    def comment(self) -> Optional[str]:
        return self._annotations.get("comment")

    @property
    def highlight(self) -> Optional[str]:
        return self._annotations.get("highlight")

    @property
    def timeline(self) -> TimelineDetails:
        return self._timeline

    @property
    def annotations(self) -> Dict[str, str]:
        return dict(self._annotations)

    @classmethod
    def from_files(cls, index: int, meta_path: str, body_path: str, annotations_paths: Optional[List[str]] = None):
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
                    with open(p, "r") as af:
                        ann_name = os.path.basename(p).replace(".txt", "")
                        ann[ann_name] = af.read()
                except Exception:
                    pass

        return cls(index, exchange, body_bytes, ann)
