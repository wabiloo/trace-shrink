# src/abr_capture_spy/har_entry.py
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from yarl import URL

from ..utils.http_utils import get_status_text
from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)

# Forward declaration for type hinting reader
# class HarReader: pass # If HarReader type hint is needed and causes circularity


def _parse_har_body(
    content_data: Dict[str, Any], response_headers: Dict[str, str]
) -> tuple[Optional[str], Optional[bytes], Optional[int], Optional[int]]:
    """Parse HAR response body data.

    Returns: (text, decoded_body, raw_size, compressed_size)
    """
    text_content = content_data.get("text")
    har_encoding_field = content_data.get("encoding")
    decoded_body_cache: Optional[bytes] = None

    if text_content is None:
        return None, None, content_data.get("size"), None

    # Decode body
    if har_encoding_field == "base64" and isinstance(text_content, str):
        try:
            decoded_body_cache = base64.b64decode(text_content)
        except Exception:
            decoded_body_cache = None
    elif isinstance(text_content, str):
        mime_type_in_content_obj = content_data.get("mimeType", "").lower()
        actual_text_encoding = "utf-8"

        if "charset=" in mime_type_in_content_obj:
            try:
                actual_text_encoding = (
                    mime_type_in_content_obj.split("charset=")[-1].split(";")[0].strip()
                )
            except IndexError:
                pass
        else:
            content_type_header = response_headers.get("Content-Type", "").lower()
            if "charset=" in content_type_header:
                try:
                    actual_text_encoding = (
                        content_type_header.split("charset=")[-1].split(";")[0].strip()
                    )
                except IndexError:
                    pass
        try:
            decoded_body_cache = text_content.encode(actual_text_encoding)
        except (LookupError, UnicodeEncodeError):
            try:
                decoded_body_cache = text_content.encode("utf-8", errors="replace")
            except Exception:
                decoded_body_cache = None
    elif isinstance(text_content, (bytes, bytearray)):
        decoded_body_cache = bytes(text_content)

    # Get text
    text = None
    if decoded_body_cache is not None:
        mime_type_from_content = content_data.get("mimeType", "").lower()
        final_encoding = "utf-8"

        if "charset=" in mime_type_from_content:
            try:
                final_encoding = (
                    mime_type_from_content.split("charset=")[-1].split(";")[0].strip()
                )
            except IndexError:
                pass
        else:
            content_type_header = response_headers.get("Content-Type", "").lower()
            if "charset=" in content_type_header:
                try:
                    final_encoding = (
                        content_type_header.split("charset=")[-1].split(";")[0].strip()
                    )
                except IndexError:
                    pass
        try:
            text = decoded_body_cache.decode(final_encoding, errors="replace")
        except LookupError:
            try:
                text = decoded_body_cache.decode("utf-8", errors="replace")
            except Exception:
                text = None
        except Exception:
            text = None

    # Get sizes
    raw_size = content_data.get("size")
    if isinstance(raw_size, int) and raw_size >= 0:
        pass
    elif decoded_body_cache is not None:
        raw_size = len(decoded_body_cache)
    else:
        raw_size = 0

    return text, decoded_body_cache, raw_size, None


class HarEntry(TraceEntry):
    """
    Represents a single entry in a HAR file, providing access to request,
    response, and timeline details.
    """

    def __init__(self, har_entry_data: Dict[str, Any], reader: Any, entry_index: int):
        """
        Initializes a HarEntry.

        Args:
            har_entry_data: The raw dictionary for the HAR entry.
            reader: The HarReader instance that this entry belongs to.
            entry_index: The index of this entry within the HAR file.
        """
        self._raw_data = har_entry_data
        self._reader = reader

        # Parse request
        request_data = har_entry_data.get("request", {})
        raw_url = request_data.get("url", "")
        try:
            url = URL(raw_url)
        except ValueError:
            url = URL("")

        request_headers_dict: Dict[str, str] = {}
        har_headers: List[Dict[str, str]] = request_data.get("headers", [])
        for h in har_headers:
            name = h.get("name")
            value = h.get("value")
            if name:
                request_headers_dict[name] = value if value is not None else ""

        request = RequestDetails(
            url=url,
            method=request_data.get("method", "GET").upper(),
            headers=request_headers_dict,
        )

        # Parse response
        response_data = har_entry_data.get("response", {})
        response_headers_dict: Dict[str, str] = {}
        har_response_headers: List[Dict[str, str]] = response_data.get("headers", [])
        for h in har_response_headers:
            name = h.get("name")
            value = h.get("value")
            if name:
                response_headers_dict[name] = value if value is not None else ""

        content_data = response_data.get("content", {})
        body_text, body_decoded, raw_size, _ = _parse_har_body(
            content_data, response_headers_dict
        )

        compressed_size = response_data.get("bodySize")
        if isinstance(compressed_size, int) and compressed_size >= 0:
            pass
        else:
            compressed_size = raw_size or 0

        content_type = content_data.get("mimeType")
        mime_type = (
            content_type.split(";")[0].strip()
            if content_type and isinstance(content_type, str)
            else None
        )

        response_body = ResponseBodyDetails(
            text=body_text,
            raw_size=raw_size,
            compressed_size=compressed_size,
            decoded_body=body_decoded,
        )

        response = ResponseDetails(
            headers=response_headers_dict,
            status_code=response_data.get("status", 0),
            mime_type=mime_type,
            content_type=content_type,
            body=response_body,
        )

        # Parse timeline
        started_date_time = har_entry_data.get("startedDateTime")
        duration_ms = har_entry_data.get("time", 0.0)

        request_start = None
        if started_date_time:
            try:
                request_start = datetime.fromisoformat(started_date_time)
            except ValueError:
                request_start = None

        response_end = None
        if request_start and duration_ms:
            response_end = request_start + timedelta(milliseconds=duration_ms)

        timeline = TimelineDetails(
            request_start=request_start,
            request_end=None,  # Not available in HAR
            response_start=None,  # Not available in HAR
            response_end=response_end,
        )

        # Entry ID
        entry_id = har_entry_data.get(
            "_id", har_entry_data.get("id", f"index-{entry_index}")
        )

        # Initialize TraceEntry
        super().__init__(
            index=entry_index,
            entry_id=str(entry_id),
            request=request,
            response=response,
            timeline=timeline,
            comment=har_entry_data.get("comment"),
            highlight=har_entry_data.get("_highlight"),
        )

    def get_raw_json(self) -> Dict[str, Any]:
        """Returns the raw JSON data for this entry."""
        return self._raw_data

    @property
    def time(
        self,
    ) -> Optional[float]:  # Total time for the entry in milliseconds from HAR spec
        """Total time for the entry in milliseconds from the HAR spec."""
        return self._raw_data.get("time")

    def __str__(self) -> str:
        return f"HarEntry(id={self.id} {self.request.method} {self.request.url} -> {self.response.status_code})"

    def __repr__(self) -> str:
        return f"<HarEntry id={self.id} {self.request.method} {self.request.url} -> {self.response.status_code}>"

    @classmethod
    def from_trace_entry(
        cls, entry: TraceEntry, entry_index: int = 0
    ) -> Dict[str, Any]:
        """
        Create a HAR entry dictionary from a TraceEntry.

        Args:
            entry: The TraceEntry to convert.
            entry_index: The index of the entry (for ID generation if needed).

        Returns:
            Dictionary representing a HAR entry.
        """
        timeline = entry.timeline
        request_start = timeline.request_start

        # Calculate duration in milliseconds
        duration_ms = 0.0
        if request_start and timeline.response_end:
            duration_ms = (
                timeline.response_end - request_start
            ).total_seconds() * 1000.0

        # Format startedDateTime as ISO 8601 string with timezone
        # HAR spec requires timezone (TZD). If missing, assume UTC (+00:00)
        if request_start is None:
            raise ValueError("request_start is required for HAR export but is None")

        iso_str = request_start.isoformat()
        # Check if timezone is present
        if request_start.tzinfo is None:
            # No timezone info, add UTC offset
            iso_str += "+00:00"
        started_date_time = iso_str

        # Convert headers
        request_headers = [
            {"name": name, "value": value}
            for name, value in entry.request.headers.items()
        ]
        response_headers = [
            {"name": name, "value": value}
            for name, value in entry.response.headers.items()
        ]

        # Parse query string
        query_params = []
        for name, value in entry.request.url.query.items():
            query_params.append({"name": name, "value": value})

        # Build request object
        request_obj: Dict[str, Any] = {
            "method": entry.request.method,
            "url": str(entry.request.url),
            "httpVersion": "HTTP/1.1",
            "headers": request_headers,
            "queryString": query_params,
            "cookies": [],
            "headersSize": sum(
                len(name) + len(value) + 4
                for name, value in entry.request.headers.items()
            ),
            "bodySize": 0,
        }

        # Build response content
        response_body = entry.response.body
        content_size = response_body.raw_size or 0
        compressed_size = response_body.compressed_size or content_size

        # entry.content already checks for override_response_content first
        is_binary = False
        try:
            content = entry.content
            if isinstance(content, bytes):
                content_text = base64.b64encode(content).decode("utf-8")
                is_binary = True
            elif isinstance(content, str):
                content_text = content
            else:
                content_text = ""
            # Update content size based on actual content (in case override was used)
            if isinstance(content, str):
                content_size = len(content.encode("utf-8"))
            elif isinstance(content, bytes):
                content_size = len(content)
            compressed_size = content_size
        except Exception:
            # Fallback only if entry.content fails and there's no override
            if not (
                hasattr(entry, "_override_response_content")
                and entry._override_response_content is not None
            ):
                content_text = response_body.text or ""
            else:
                content_text = ""

        # Determine if body should be base64 encoded based on mime type (if not already binary)
        if content_text and not is_binary:
            mime_type = entry.response.mime_type or ""
            if not cls._is_text_content_for_har(mime_type, content_text):
                try:
                    content_bytes = content_text.encode("utf-8")
                    content_text = base64.b64encode(content_bytes).decode("utf-8")
                    is_binary = True
                except Exception:
                    pass

        content_obj: Dict[str, Any] = {
            "size": content_size,
            "mimeType": entry.response.content_type or "",
        }

        if is_binary:
            content_obj["encoding"] = "base64"
            content_obj["text"] = content_text
        else:
            content_obj["text"] = content_text
            content_obj["compression"] = max(0, content_size - compressed_size)

        # Build response object
        response_obj: Dict[str, Any] = {
            "status": entry.response.status_code,
            "statusText": get_status_text(entry.response.status_code),
            "httpVersion": "HTTP/1.1",
            "headers": response_headers,
            "cookies": [],
            "content": content_obj,
            "redirectURL": "",
            "headersSize": sum(
                len(name) + len(value) + 4
                for name, value in entry.response.headers.items()
            ),
            "bodySize": compressed_size,
        }

        # Build timings
        timings = {
            "blocked": -1,
            "dns": -1,
            "connect": -1,
            "send": -1,
            "wait": -1,
            "receive": -1,
        }

        # Safely get timeline properties (they may raise NotImplementedError for HAR entries)
        try:
            response_start = timeline.response_start
        except NotImplementedError:
            response_start = None

        try:
            request_end = timeline.request_end
        except NotImplementedError:
            request_end = None

        response_end = timeline.response_end  # This is always available

        if request_start and response_start and response_end:
            if request_end:
                send_time = (request_end - request_start).total_seconds() * 1000
                timings["send"] = max(0, send_time)
            if response_start:
                wait_time = (
                    response_start - (request_end or request_start)
                ).total_seconds() * 1000
                timings["wait"] = max(0, wait_time)
            if response_end:
                receive_time = (response_end - response_start).total_seconds() * 1000
                timings["receive"] = max(0, receive_time)

        har_entry: Dict[str, Any] = {
            "startedDateTime": started_date_time,
            "time": duration_ms,
            "request": request_obj,
            "response": response_obj,
            "cache": {},
            "timings": timings,
        }

        if entry.comment:
            har_entry["comment"] = entry.comment

        entry_id = entry.id
        if entry_id and not entry_id.startswith("index-"):
            har_entry["_id"] = entry_id

        return har_entry

    @staticmethod
    def _is_text_content_for_har(mime_type: str, content: str) -> bool:
        """Determine if content should be treated as text for HAR format."""
        text_types = [
            "text/",
            "application/json",
            "application/xml",
            "application/javascript",
            "application/vnd.apple.mpegurl",
            "application/dash+xml",
        ]
        mime_lower = mime_type.lower()
        return any(mime_lower.startswith(prefix) for prefix in text_types)
