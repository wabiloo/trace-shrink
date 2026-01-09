from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from yarl import URL

from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)


class _BodyLoggerRequestDetails(RequestDetails):
    """Implementation of RequestDetails for a bodylogger entry."""

    def __init__(self, record_data: Dict[str, Any], parent_entry: "BodyLoggerEntry"):
        self._data = record_data
        self._parent_entry = parent_entry

    @property
    def url(self) -> URL:
        """Construct the URL from the record data."""
        # The request_line is the path, we need to construct full URL
        request_line = self._data.get("request_line", "")

        # Derive host from first path segment
        req_line = request_line.lstrip("/")
        if "/" in req_line:
            host, path_after_host = req_line.split("/", 1)
            path_after_host = "/" + path_after_host
        else:
            host, path_after_host = req_line, "/"

        log_type = self._data.get("log_type", "").lower()

        # Construct URL with log_type appended to host
        url_str = f"http://{host}-{log_type}{path_after_host}"

        # Add query parameters if present
        query_params = self._data.get("query_params", "")
        if query_params:
            url_str += f"?{query_params}"

        try:
            return URL(url_str)
        except ValueError:
            return URL("")

    @property
    def headers(self) -> Dict[str, str]:
        """Return request headers."""
        hdrs = self._data.get("headers", {}).copy()

        # Add correlation-id as header
        correlation_id = self._data.get("correlation_id")
        if correlation_id is not None:
            hdrs["correlation-id"] = str(correlation_id)

        # Map x-sessionid to BPK-Session if present
        if "x-sessionid" in hdrs:
            hdrs["BPK-Session"] = hdrs["x-sessionid"]

        # Map x-serviceid to BPK-Service if present
        if "x-serviceid" in hdrs:
            hdrs["BPK-Service"] = hdrs["x-serviceid"]

        return hdrs

    @property
    def method(self) -> str:
        """Return HTTP method (always GET for bodylogger)."""
        return "GET"


class _BodyLoggerResponseBodyDetails(ResponseBodyDetails):
    """Implementation of ResponseBodyDetails for a bodylogger entry."""

    def __init__(self, record_data: Dict[str, Any], parent_entry: "BodyLoggerEntry"):
        self._data = record_data
        self._parent_entry = parent_entry
        self._decoded_body_cache: Optional[bytes] = None

    def _get_decoded_body(self) -> Optional[bytes]:
        """Get the decoded body as bytes."""
        if self._decoded_body_cache is not None:
            return self._decoded_body_cache

        body = self._data.get("body")
        if body and isinstance(body, str):
            try:
                self._decoded_body_cache = body.encode("utf-8")
                return self._decoded_body_cache
            except Exception:
                return None
        return None

    @property
    def text(self) -> Optional[str]:
        """Return the response body as text."""
        return self._data.get("body")

    @property
    def raw_size(self) -> Optional[int]:
        """Return the raw size of the response body."""
        body = self._data.get("body")
        if body:
            return len(body.encode("utf-8"))
        return None

    @property
    def compressed_size(self) -> Optional[int]:
        """Return the compressed size (same as raw for bodylogger)."""
        return self.raw_size


class _BodyLoggerResponseDetails(ResponseDetails):
    """Implementation of ResponseDetails for a bodylogger entry."""

    def __init__(self, record_data: Dict[str, Any], parent_entry: "BodyLoggerEntry"):
        self._data = record_data
        self._parent_entry = parent_entry
        self._body_details = _BodyLoggerResponseBodyDetails(record_data, parent_entry)

    @property
    def headers(self) -> Dict[str, str]:
        """Return response headers."""
        hdrs = {"Content-Type": self._data.get("content_type", "text/plain")}

        # Add HLS-specific headers if applicable
        body = self._data.get("body", "")
        if self._data.get("content_type") == "application/x-mpegURL":
            import re

            # Extract HLS-MediaSeq
            media_seq_match = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", body)
            if media_seq_match:
                hdrs["HLS-MediaSeq"] = media_seq_match.group(1)

            # Extract HLS-PDT
            pdt_match = re.search(r"#EXT-X-PROGRAM-DATE-TIME:([^,\n]+)", body)
            if pdt_match:
                hdrs["HLS-PDT"] = pdt_match.group(1)

        return hdrs

    @property
    def mime_type(self) -> Optional[str]:
        """Return the MIME type."""
        ct = self._data.get("content_type")
        return ct.split(";")[0].strip() if ct and isinstance(ct, str) else None

    @property
    def content_type(self) -> Optional[str]:
        """Return the full content type."""
        return self._data.get("content_type")

    @property
    def body(self) -> ResponseBodyDetails:
        """Return body details."""
        return self._body_details

    @property
    def status_code(self) -> int:
        """Return HTTP status code (always 200 for bodylogger)."""
        return 200


class _BodyLoggerTimelineDetails(TimelineDetails):
    """Implementation of TimelineDetails for a bodylogger entry."""

    def __init__(self, timestamp: datetime, request_time: float):
        self._timestamp = timestamp
        self._request_time = request_time  # in seconds

    @property
    def request_start(self) -> Optional[datetime]:
        """Return the request start time."""
        return self._timestamp

    @property
    def request_end(self) -> Optional[datetime]:
        """Not available in bodylogger format."""
        return None

    @property
    def response_start(self) -> Optional[datetime]:
        """Not available in bodylogger format."""
        return None

    @property
    def response_end(self) -> Optional[datetime]:
        """Return the response end time (request_start + request_time)."""
        if self._timestamp is not None:
            return self._timestamp + timedelta(seconds=self._request_time)
        return None


class BodyLoggerEntry(TraceEntry):
    """
    Represents a single entry from a bodylogger file, providing access to request,
    response, and timeline details.
    """

    def __init__(self, record_data: Dict[str, Any], reader: Any, entry_index: int):
        """
        Initializes a BodyLoggerEntry.

        Args:
            record_data: The raw dictionary for the bodylogger record.
            reader: The BodyLoggerReader instance that this entry belongs to.
            entry_index: The index of this entry within the bodylogger file.
        """
        self._raw_data = record_data
        self._reader = reader
        self._index = entry_index
        self._request = _BodyLoggerRequestDetails(record_data, self)
        self._response = _BodyLoggerResponseDetails(record_data, self)
        self._timeline = _BodyLoggerTimelineDetails(
            record_data.get("timestamp"), record_data.get("request_time", 0.0)
        )

    @property
    def index(self) -> int:
        """The zero-based index of the entry in the archive."""
        return self._index

    @property
    def id(self) -> str:
        """A unique identifier for the entry based on its position in the log file."""
        return str(self._index)

    @property
    def request(self) -> RequestDetails:
        """Details of the HTTP request."""
        return self._request

    @property
    def response(self) -> ResponseDetails:
        """Details of the HTTP response."""
        return self._response

    @property
    def comment(self) -> Optional[str]:
        """Return the comment. Defaults to log type if not explicitly set."""
        # Check for explicitly set comment first
        if "comment" in self._raw_data:
            return self._raw_data["comment"]
        # Fall back to log_type as default
        return self._raw_data.get("log_type")

    @property
    def highlight(self) -> Optional[str]:
        """Return the highlight style if set."""
        return self._raw_data.get("highlight")

    @property
    def timeline(self) -> TimelineDetails:
        """Timeline details of the HTTP exchange."""
        return self._timeline

    def get_raw_data(self) -> Dict[str, Any]:
        """Returns the raw data for this entry."""
        return self._raw_data

    @property
    def service_id(self) -> Optional[str]:
        """Return the service ID for this entry."""
        return self._raw_data.get("service_id")

    @property
    def session_id(self) -> Optional[str]:
        """Return the session ID for this entry."""
        return self._raw_data.get("session_id")

    def set_comment(self, comment: str) -> None:
        """
        Set a comment on this entry (in-memory only, cannot be persisted).

        Args:
            comment: The comment text to add to this entry.
        """
        self._raw_data["comment"] = comment

    def set_highlight(self, highlight: str) -> None:
        """
        Set a highlight style on this entry (in-memory only, cannot be persisted).

        Args:
            highlight: The highlight style (e.g., 'red', 'yellow', 'strike').
        """
        self._raw_data["highlight"] = highlight

    @property
    def correlation_id(self) -> int:
        """Return the correlation ID for this entry."""
        return self._raw_data.get("correlation_id", 0)
