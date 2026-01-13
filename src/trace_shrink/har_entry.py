# src/abr_capture_spy/har_entry.py
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

        # Merge annotation cache headers (from add_response_header)
        if hasattr(self._parent_entry, "_annotation_cache"):
            hdrs.update(
                self._parent_entry._annotation_cache.get("response_headers", {})
            )

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

    def set_highlight(self, highlight: str) -> None:
        """
        Set a highlight style on this entry.

        Supported values:
        - "red" (0)
        - "yellow" (1)
        - "green" (2)
        - "blue" (3)
        - "purple" (4)
        - "grey" (5)
        - "strike" (strike-through)

        Note: HAR format does not natively support highlighting/coloring entries.
        The highlight is stored in a custom "_highlight" field and will be preserved
        when converting to Proxyman format.

        Args:
            highlight: The highlight style to apply.

        Raises:
            ValueError: If an invalid highlight value is provided.
        """
        from .highlight import validate_highlight

        validate_highlight(highlight)
        # Use TraceEntry's override mechanism
        super().set_highlight(highlight)

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

        # Format startedDateTime as ISO 8601 string
        started_date_time = (
            request_start.isoformat() if request_start else datetime.now().isoformat()
        )

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
            "statusText": cls._get_status_text(entry.response.status_code),
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

    @staticmethod
    def _get_status_text(status_code: int) -> str:
        """Get HTTP status text for a status code."""
        status_texts = {
            200: "OK",
            201: "Created",
            204: "No Content",
            301: "Moved Permanently",
            302: "Found",
            304: "Not Modified",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
        }
        return status_texts.get(status_code, "Unknown")
