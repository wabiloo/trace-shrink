# src/abr_capture_spy/har_entry.py
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from yarl import URL

from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)

# Forward declaration for type hinting reader
# class HarReader: pass # If HarReader type hint is needed and causes circularity


class _HarRequestDetails(RequestDetails):
    """Implementation of RequestDetails for a HAR entry."""

    def __init__(
        self, har_entry_request_data: Dict[str, Any], parent_entry: "HarEntry"
    ):
        self._data = har_entry_request_data
        self._parent_entry = parent_entry

    @property
    def url(self) -> URL:
        raw_url = self._data.get("url", "")
        try:
            return URL(raw_url)
        except ValueError:
            return URL("")

    @property
    def headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {}
        har_headers: List[Dict[str, str]] = self._data.get("headers", [])
        for h in har_headers:
            name = h.get("name")
            value = h.get("value")
            if name:
                hdrs[name] = value if value is not None else ""
        return hdrs

    @property
    def method(self) -> str:
        return self._data.get("method", "GET").upper()


class _HarResponseBodyDetails(ResponseBodyDetails):
    """Implementation of ResponseBodyDetails for a HAR entry."""

    def __init__(
        self, har_entry_response_content_data: Dict[str, Any], parent_entry: "HarEntry"
    ):
        self._data = har_entry_response_content_data
        self._parent_entry = parent_entry
        self._decoded_body_cache: Optional[bytes] = None

    def _get_decoded_body(self) -> Optional[bytes]:
        if self._decoded_body_cache is not None:
            # Ensure cache is returned only once to avoid issues with mutable objects if we alter it.
            # For bytes, it's fine, but good practice if it were, e.g., a stream.
            return self._decoded_body_cache

        text_content = self._data.get("text")
        har_encoding_field = self._data.get("encoding")  # e.g., "base64"

        if text_content is None:
            # If text is None but size > 0, it implies body was fetched but not stored, or is binary only.
            # HAR viewers often show this for images. For our library, if text is None, body is None.
            return None

        if har_encoding_field == "base64" and isinstance(text_content, str):
            try:
                self._decoded_body_cache = base64.b64decode(text_content)
            except Exception:
                return None
        elif isinstance(text_content, str):
            # If not base64 encoded according to HAR, determine actual text encoding.
            # Priority: 1. charset in response.content.mimeType, 2. charset in Content-Type header.
            mime_type_in_content_obj = self._data.get("mimeType", "").lower()
            actual_text_encoding = "utf-8"  # Default

            parsed_from_content_mime = False
            if "charset=" in mime_type_in_content_obj:
                try:
                    actual_text_encoding = (
                        mime_type_in_content_obj.split("charset=")[-1]
                        .split(";")[0]
                        .strip()
                    )
                    parsed_from_content_mime = True
                except IndexError:
                    pass

            if not parsed_from_content_mime:  # Fallback to actual HTTP header
                response_headers = self._parent_entry.response.headers
                content_type_header = response_headers.get("Content-Type", "").lower()
                if "charset=" in content_type_header:
                    try:
                        actual_text_encoding = (
                            content_type_header.split("charset=")[-1]
                            .split(";")[0]
                            .strip()
                        )
                    except IndexError:
                        pass
            try:
                self._decoded_body_cache = text_content.encode(actual_text_encoding)
            except (LookupError, UnicodeEncodeError):
                try:
                    self._decoded_body_cache = text_content.encode(
                        "utf-8", errors="replace"
                    )
                except Exception:
                    return None
        elif isinstance(text_content, (bytes, bytearray)):
            # If it's already bytes (non-standard for HAR JSON text field but defensive)
            self._decoded_body_cache = bytes(text_content)
        else:
            # Content is not str or bytes, or encoding type is unknown/unhandled
            return None

        return self._decoded_body_cache

    @property
    def text(self) -> Optional[str]:
        decoded_bytes = self._get_decoded_body()
        if decoded_bytes is None:
            return None

        mime_type_from_content = self._data.get("mimeType", "").lower()
        final_encoding = "utf-8"  # Default

        if "charset=" in mime_type_from_content:
            try:
                final_encoding = (
                    mime_type_from_content.split("charset=")[-1].split(";")[0].strip()
                )
            except IndexError:
                pass
        else:
            response_headers = self._parent_entry.response.headers
            content_type_header = response_headers.get("Content-Type", "").lower()
            if "charset=" in content_type_header:
                try:
                    final_encoding = (
                        content_type_header.split("charset=")[-1].split(";")[0].strip()
                    )
                except IndexError:
                    pass
        try:
            return decoded_bytes.decode(final_encoding, errors="replace")
        except LookupError:
            try:
                return decoded_bytes.decode("utf-8", errors="replace")
            except Exception:
                return None
        except Exception:
            return None

    @property
    def raw_size(self) -> Optional[int]:
        size = self._data.get("size")  # This is uncompressed size in HAR content object
        if (
            isinstance(size, int) and size >= 0
        ):  # size can be 0 for empty body, -1 usually means unknown
            return size
        # If size is -1 or missing, try to get it from the decoded body length
        decoded_body = self._get_decoded_body()
        return len(decoded_body) if decoded_body is not None else 0

    @property
    def compressed_size(self) -> Optional[int]:
        # HAR response object's bodySize is the transferred size.
        # response.content.compression tells how many bytes were saved by compression.
        # if compression is 0 or undefined, bodySize == content.size.
        body_size = self._parent_entry._raw_data.get("response", {}).get("bodySize")
        if isinstance(body_size, int) and body_size >= 0:
            return body_size
        return 0  # Default to 0 if not present or invalid


class _HarResponseDetails(ResponseDetails):
    """Implementation of ResponseDetails for a HAR entry."""

    def __init__(
        self, har_entry_response_data: Dict[str, Any], parent_entry: "HarEntry"
    ):
        self._data = har_entry_response_data
        self._parent_entry = parent_entry
        self._body_details = _HarResponseBodyDetails(
            self._data.get("content", {}), parent_entry
        )

    @property
    def headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {}
        har_headers: List[Dict[str, str]] = self._data.get("headers", [])
        for h in har_headers:
            name = h.get("name")
            value = h.get("value")
            if name:
                hdrs[name] = value if value is not None else ""
        return hdrs

    @property
    def mime_type(self) -> Optional[str]:
        ct = self._data.get("content", {}).get("mimeType")
        return ct.split(";")[0].strip() if ct and isinstance(ct, str) else None

    @property
    def content_type(self) -> Optional[str]:
        return self._data.get("content", {}).get("mimeType")

    @property
    def body(self) -> ResponseBodyDetails:
        return self._body_details

    @property
    def status_code(self) -> int:
        return self._data.get("status", 0)


class _HarTimelineDetails(TimelineDetails):
    """Implementation of TimelineDetails for a HAR entry."""

    def __init__(self, started_date_time: str, duration_ms: float):
        self._started_date_time = started_date_time
        self._duration_ms = duration_ms

    @property
    def request_start(self) -> Optional[datetime]:
        if self._started_date_time:
            try:
                return datetime.fromisoformat(self._started_date_time)
            except ValueError:
                return None
        return None

    @property
    def request_end(self) -> Optional[datetime]:
        raise NotImplementedError("Not implemented - not available in HAR")

    @property
    def response_start(self) -> Optional[datetime]:
        raise NotImplementedError("Not implemented - not available in HAR")

    @property
    def response_end(self) -> Optional[datetime]:
        if self._started_date_time and self._duration_ms:
            return self.request_start + timedelta(milliseconds=self._duration_ms)
        return None


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
        self._index = entry_index
        self._request = _HarRequestDetails(self._raw_data.get("request", {}), self)
        self._response = _HarResponseDetails(self._raw_data.get("response", {}), self)
        self._timeline = _HarTimelineDetails(
            self._raw_data.get("startedDateTime"), self._raw_data.get("time")
        )

    @property
    def index(self) -> int:
        """The zero-based index of the entry in the archive."""
        return self._index

    @property
    def id(self) -> str:
        """
        A unique identifier for the entry, if available.
        In HAR, this can be a custom field, but is not standard.
        Falls back to the entry's index as a string.
        """
        # HAR does not have a standard entry ID like proxyman.
        # Check for a common custom field `_id` or `id`.
        return self._raw_data.get(
            "_id", self._raw_data.get("id", f"index-{self.index}")
        )

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
        """An optional comment for the entry."""
        return self._raw_data.get("comment")

    @property
    def timeline(self) -> TimelineDetails:
        """Timeline details of the HTTP exchange."""
        return self._timeline

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
