# src/abr_capture_snoop/har_entry.py
import base64
import json  # For parsing postData.text if it's JSON
from typing import Any, Dict, List, Optional, Union

from yarl import URL

from .capture_entry import (
    CaptureEntry,
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimingsDetails,
)

# Forward declaration for type hinting reader
# class HarReader: pass # If HarReader type hint is needed and causes circularity


class _HarRequestDetails(RequestDetails):
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

    @property
    def body(self) -> Optional[bytes]:
        post_data = self._data.get("postData")
        if not post_data or "text" not in post_data:
            return None

        text_content = post_data["text"]
        mime_type = post_data.get("mimeType", "").lower()
        # HAR spec doesn't have a standard 'encoding' field for postData like for response content.
        # It's usually implied by mimeType or assumed to be utf-8 for text.
        # If mime_type explicitly says it's base64, that would be non-standard but possible.

        if isinstance(text_content, str):
            # Determine encoding from mimeType if charset is present
            body_encoding = "utf-8"  # Default
            if "charset=" in mime_type:
                try:
                    body_encoding = (
                        mime_type.split("charset=")[-1].split(";")[0].strip()
                    )
                except IndexError:
                    pass  # Stick to default
            try:
                return text_content.encode(body_encoding)
            except (LookupError, UnicodeEncodeError):
                try:  # Fallback
                    return text_content.encode("utf-8", errors="replace")
                except Exception:
                    return None
        # Although less common for postData.text to be pre-encoded bytes in JSON, handle if it is.
        elif isinstance(text_content, bytes):
            return text_content
        return None


class _HarResponseBodyDetails(ResponseBodyDetails):
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


class _HarTimingsDetails(TimingsDetails):
    def __init__(self, har_entry_timings_data: Dict[str, Any]):
        self._data = har_entry_timings_data

    def _get_timing_in_seconds(self, key: str) -> Optional[float]:
        value = self._data.get(key, -1)
        if isinstance(value, (int, float)) and value >= 0:
            return value / 1000.0  # Convert ms to seconds
        return None

    @property
    def blocked(self) -> Optional[float]:
        return self._get_timing_in_seconds("blocked")

    @property
    def dns(self) -> Optional[float]:
        return self._get_timing_in_seconds("dns")

    @property
    def connect(self) -> Optional[float]:
        return self._get_timing_in_seconds("connect")

    @property
    def ssl(self) -> Optional[float]:
        return self._get_timing_in_seconds("ssl")

    @property
    def send(self) -> Optional[float]:
        return self._get_timing_in_seconds("send")

    @property
    def wait(self) -> Optional[float]:
        return self._get_timing_in_seconds("wait")

    @property
    def receive(self) -> Optional[float]:
        return self._get_timing_in_seconds("receive")

    @property
    def total_time(self) -> Optional[float]:
        # HAR entry.time is the total time for the entry in ms.
        # Not part of the 'timings' sub-object usually, but related.
        # This should ideally be taken from the parent HarEntry's .time property.
        # For now, this class only sees the timings sub-object.
        # Fallback: sum of components if available and entry.time is not used directly.
        if (
            self._parent_entry
            and hasattr(self._parent_entry, "time")
            and self._parent_entry.time is not None
        ):
            return self._parent_entry.time / 1000.0

        components = [
            self.blocked,
            self.dns,
            self.connect,
            self.send,
            self.wait,
            self.receive,
        ]
        valid_components = [c for c in components if c is not None]
        return sum(valid_components) if valid_components else None


class HarEntry(CaptureEntry):
    def __init__(self, har_entry_data: Dict[str, Any], reader: Any, entry_index: int):
        self._raw_data = har_entry_data
        self._reader = reader
        self._entry_index = entry_index  # Store index for a more stable ID

        self._request_details = _HarRequestDetails(
            self._raw_data.get("request", {}), self
        )
        self._response_details = _HarResponseDetails(
            self._raw_data.get("response", {}), self
        )
        # Pass self to _HarTimingsDetails if it needs to access parent HarEntry.time
        self._timing_details = _HarTimingsDetails(
            self._raw_data.get("timings", {}),
            self if hasattr(_HarTimingsDetails, "total_time") else None,
        )

    @property
    def index(self) -> int:
        return self._entry_index

    @property
    def id(self) -> str:
        if self._raw_data.get("_id"):
            return self._raw_data.get("_id")
        # Use the index provided by the reader for a stable, unique ID within the HAR file.
        # startedDateTime can be non-unique if multiple requests start at the exact same millisecond.
        return f"index-{self._entry_index}"

    @property
    def request(self) -> RequestDetails:
        return self._request_details

    @property
    def response(self) -> ResponseDetails:
        return self._response_details

    @property
    def comment(self) -> Optional[str]:
        return self._raw_data.get("comment")

    @property
    def timings(self) -> TimingsDetails:
        return self._timing_details

    def get_raw_json(self) -> Dict[str, Any]:
        return self._raw_data

    @property
    def started_date_time(self) -> str:
        return self._raw_data.get("startedDateTime", "")

    @property
    def time(
        self,
    ) -> Optional[float]:  # Total time for the entry in milliseconds from HAR spec
        t = self._raw_data.get("time", -1)
        return t if isinstance(t, (int, float)) and t >= 0 else None

    def __str__(self) -> str:
        return f"HarEntry({self.id} {self.request.method} {str(self.request.url)} -> {self.response.status_code})"

    def __repr__(self) -> str:
        return f"<HarEntry id={self.id} url={str(self.request.url)}>"


# Need to update _HarTimingsDetails constructor if it takes parent_entry
_HarTimingsDetails.__init__ = (
    lambda self, har_entry_timings_data, parent_entry=None: setattr(
        self, "_data", har_entry_timings_data
    )
    or setattr(self, "_parent_entry", parent_entry)
)
