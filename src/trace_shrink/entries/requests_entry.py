from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, Optional

import yarl

from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)

if TYPE_CHECKING:
    from requests import Response


class RequestsResponseTraceEntry(TraceEntry):
    """TraceEntry adapter that wraps a requests.Response object.

    This class provides a TraceEntry interface for a requests.Response object,
    allowing it to be used with trace_shrink APIs that expect TraceEntry instances.
    Note: This is a read-only entry type (no corresponding Writer class), but
    mutations via the parent TraceEntry class are fully supported.
    """

    def __init__(
        self, response: "Response", index: int = 0, entry_id: Optional[str] = None
    ):
        """Create a TraceEntry from a requests.Response object.

        Args:
            response: The requests.Response object to wrap
            index: The index of this entry (default: 0)
            entry_id: Optional unique identifier (default: str(index))
        """
        # Store the original response for access to elapsed time and reason
        # Note: We use _original_response because TraceEntry.__init__ will set self._response
        self._original_response = response

        # Parse request URL
        try:
            url = yarl.URL(str(response.request.url))
        except Exception:
            url = yarl.URL("")

        # Extract request headers
        request_headers: Dict[str, str] = {}
        if hasattr(response.request, "headers"):
            request_headers = dict(response.request.headers)

        # Extract request method
        method = getattr(response.request, "method", "GET")

        # Extract request body if available
        request_body: Optional[bytes] = None
        if hasattr(response.request, "body") and response.request.body:
            if isinstance(response.request.body, bytes):
                request_body = response.request.body
            elif isinstance(response.request.body, str):
                request_body = response.request.body.encode("utf-8")

        request = RequestDetails(
            url=url,
            method=method.upper(),
            headers=request_headers,
            body=request_body,
        )

        # Extract response headers
        response_headers: Dict[str, str] = dict(response.headers)

        # Extract content type and mime type
        content_type = response_headers.get("Content-Type", "")
        mime_type = None
        if content_type:
            mime_type = content_type.split(";")[0].strip()

        # Extract response body
        body_text: Optional[str] = None
        body_bytes: Optional[bytes] = None
        try:
            body_text = response.text
            body_bytes = response.content
        except Exception:
            pass

        raw_size = len(body_bytes) if body_bytes is not None else 0

        response_body = ResponseBodyDetails(
            text=body_text,
            raw_size=raw_size,
            compressed_size=raw_size,
            decoded_body=body_bytes,
        )

        response_details = ResponseDetails(
            headers=response_headers,
            status_code=response.status_code,
            mime_type=mime_type,
            content_type=content_type if content_type else None,
            body=response_body,
        )

        # Create timeline from elapsed time
        request_start: Optional[datetime] = None
        response_end: Optional[datetime] = None

        # Try to get elapsed time
        elapsed_ms = 0
        if hasattr(response, "elapsed") and response.elapsed:
            elapsed_ms = int(response.elapsed.total_seconds() * 1000)

        # Use current time as response_end, calculate request_start from elapsed
        if elapsed_ms > 0:
            response_end = datetime.now(timezone.utc)
            request_start = response_end - timedelta(milliseconds=elapsed_ms)

        timeline = TimelineDetails(
            request_start=request_start,
            request_end=None,
            response_start=None,
            response_end=response_end,
        )

        # Initialize TraceEntry
        super().__init__(
            index=index,
            entry_id=entry_id or str(index),
            request=request,
            response=response_details,
            timeline=timeline,
        )

    @property
    def elapsed_ms(self) -> int:
        """Get the elapsed time in milliseconds from the response."""
        try:
            elapsed = getattr(self._original_response, "elapsed", None)
            if elapsed is not None and hasattr(elapsed, "total_seconds"):
                return int(elapsed.total_seconds() * 1000)
        except Exception:
            pass
        return 0

    @property
    def reason(self) -> Optional[str]:
        """Get the HTTP reason phrase from the response."""
        return getattr(self._original_response, "reason", None)
