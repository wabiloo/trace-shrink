import re
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


def _parse_bodylogger_url(record_data: Dict[str, Any]) -> URL:
    """Parse URL from bodylogger record data."""
    request_line = record_data.get("request_line", "")
    req_line = request_line.lstrip("/")
    if "/" in req_line:
        host, path_after_host = req_line.split("/", 1)
        path_after_host = "/" + path_after_host
    else:
        host, path_after_host = req_line, "/"

    log_type = record_data.get("log_type", "").lower()
    url_str = f"http://{host}-{log_type}{path_after_host}"

    query_params = record_data.get("query_params", "")
    if query_params:
        url_str += f"?{query_params}"

    try:
        return URL(url_str)
    except ValueError:
        return URL("")


def _parse_bodylogger_request_headers(record_data: Dict[str, Any]) -> Dict[str, str]:
    """Parse request headers from bodylogger record data."""
    hdrs = record_data.get("headers", {}).copy()

    correlation_id = record_data.get("correlation_id")
    if correlation_id is not None:
        hdrs["correlation-id"] = str(correlation_id)

    if "x-sessionid" in hdrs:
        hdrs["BPK-Session"] = hdrs["x-sessionid"]

    if "x-serviceid" in hdrs:
        hdrs["BPK-Service"] = hdrs["x-serviceid"]

    return hdrs


def _parse_bodylogger_response_headers(record_data: Dict[str, Any]) -> Dict[str, str]:
    """Parse response headers from bodylogger record data."""
    hdrs = {"Content-Type": record_data.get("content_type", "text/plain")}

    body = record_data.get("body", "")
    if record_data.get("content_type") == "application/x-mpegURL":
        media_seq_match = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", body)
        if media_seq_match:
            hdrs["HLS-MediaSeq"] = media_seq_match.group(1)

        pdt_match = re.search(r"#EXT-X-PROGRAM-DATE-TIME:([^,\n]+)", body)
        if pdt_match:
            hdrs["HLS-PDT"] = pdt_match.group(1)

    return hdrs


def parse_bodylogger_entry(
    record_data: Dict[str, Any], reader: Any, entry_index: int
) -> "BodyLoggerEntry":
    """
    Parse a bodylogger record into a BodyLoggerEntry.

    Args:
        record_data: The raw dictionary for the bodylogger record.
        reader: The BodyLoggerReader instance (for compatibility, not used).
        entry_index: The index of this entry within the bodylogger file.

    Returns:
        BodyLoggerEntry: A BodyLoggerEntry instance with parsed data.
    """
    # Parse request
    url = _parse_bodylogger_url(record_data)
    request_headers = _parse_bodylogger_request_headers(record_data)
    request = RequestDetails(
        url=url,
        method="GET",
        headers=request_headers,
    )

    # Parse response
    body_text = record_data.get("body")
    body_size = len(body_text.encode("utf-8")) if body_text else 0
    
    content_type = record_data.get("content_type")
    mime_type = content_type.split(";")[0].strip() if content_type and isinstance(content_type, str) else None
    
    response_body = ResponseBodyDetails(
        text=body_text,
        raw_size=body_size,
        compressed_size=body_size,
    )

    response_headers = _parse_bodylogger_response_headers(record_data)
    response = ResponseDetails(
        headers=response_headers,
        status_code=200,
        mime_type=mime_type,
        content_type=content_type,
        body=response_body,
    )

    # Parse timeline
    timestamp = record_data.get("timestamp")
    request_time = record_data.get("request_time", 0.0)
    request_start = timestamp - timedelta(seconds=request_time) if timestamp else None

    timeline = TimelineDetails(
        request_start=request_start,
        request_end=None,
        response_start=None,
        response_end=timestamp,
    )

    # Default comment is log_type
    comment = record_data.get("comment") or record_data.get("log_type")

    # Create BodyLoggerEntry
    entry = BodyLoggerEntry(
        index=entry_index,
        entry_id=str(entry_index),
        request=request,
        response=response,
        timeline=timeline,
        comment=comment,
        highlight=record_data.get("highlight"),
    )

    # Store raw data and reader reference for backward compatibility
    entry._raw_data = record_data
    entry._reader = reader

    return entry


class BodyLoggerEntry(TraceEntry):
    """
    Represents a single entry from a bodylogger file.
    
    This is a TraceEntry with bodylogger-specific properties for backward compatibility.
    """

    def get_raw_data(self) -> Dict[str, Any]:
        """Returns the raw data for this entry."""
        return getattr(self, "_raw_data", {})

    @property
    def service_id(self) -> Optional[str]:
        """Return the service ID for this entry."""
        raw_data = self.get_raw_data()
        return raw_data.get("service_id")

    @property
    def session_id(self) -> Optional[str]:
        """Return the session ID for this entry."""
        raw_data = self.get_raw_data()
        return raw_data.get("session_id")

    @property
    def correlation_id(self) -> int:
        """Return the correlation ID for this entry."""
        raw_data = self.get_raw_data()
        return raw_data.get("correlation_id", 0)
