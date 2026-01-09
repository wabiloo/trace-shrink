import base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from yarl import URL

from .highlight import HIGHLIGHT_COLOR_MAP, validate_highlight
from .trace_entry import (
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimelineDetails,
    TraceEntry,
)

# Forward declaration for type hinting reader if ProxymanLogV2Reader is in a separate file
# from .proxyman_log_reader import ProxymanLogV2Reader # Causes circular import if in same file or __init__

# --- Helper classes for ProxymanLogV2Entry ---


class _ProxymanRequestDetails(RequestDetails):
    """Implementation of RequestDetails for a Proxyman entry."""

    def __init__(self, entry_data: Dict[str, Any], parent_entry: "ProxymanLogV2Entry"):
        self._data = entry_data.get("request", {})
        self._parent_entry = (
            parent_entry  # To access ._raw_data or ._reader if needed for body
        )

    @property
    def url(self) -> URL:
        # Proxyman has 'fullPath' which is usually the complete URL.
        # It also has 'host', 'uri', 'scheme', 'port'.
        # We should construct the most reliable URL from these.
        full_path_str = self._data.get("fullPath")
        if full_path_str:
            try:
                return URL(full_path_str)
            except ValueError:
                pass  # Fallback if fullPath is malformed

        # Fallback: Construct from parts if fullPath is missing or invalid
        scheme = self._data.get("scheme", "http")  # Default to http if not specified
        host = self._data.get("host")
        port = self._data.get("port")
        path_query = self._data.get("uri", "/")  # uri in Proxyman is path + query

        if not host:
            return URL(
                path_query
            )  # If no host, it might be a path-only or malformed entry

        url_str = f"{scheme}://{host}"
        if port and not (
            (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        ):
            url_str += f":{port}"
        url_str += path_query
        return URL(url_str)

    @property
    def headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {}
        header_entries: List[Dict[str, Any]] = self._data.get("header", {}).get(
            "entries", []
        )
        for entry in header_entries:
            key_info = entry.get("key", {})
            key_name = key_info.get("name")
            value = entry.get("value")
            if key_name is not None and value is not None:
                hdrs[str(key_name)] = str(value)
        return hdrs

    @property
    def method(self) -> str:
        # Default to GET if not specified, though it should always be there.
        return self._data.get("method", {}).get("name", "GET").upper()

    @property
    def body(self) -> Optional[bytes]:
        # Proxyman stores request body in request.bodyData (base64 encoded)
        body_data_b64 = self._data.get("bodyData")
        if body_data_b64 and isinstance(body_data_b64, str):
            try:
                return base64.b64decode(body_data_b64)
            except Exception:
                return None  # Or log error
        return None


class _ProxymanResponseBodyDetails(ResponseBodyDetails):
    """Implementation of ResponseBodyDetails for a Proxyman entry."""

    def __init__(self, entry_data: Dict[str, Any], parent_entry: "ProxymanLogV2Entry"):
        self._data = entry_data.get("response", {})
        self._parent_entry = parent_entry
        self._decoded_body_cache: Optional[bytes] = None

    def _get_decoded_body(self) -> Optional[bytes]:
        if self._decoded_body_cache is not None:
            return self._decoded_body_cache

        body_data_b64 = self._data.get("bodyData")
        if body_data_b64 and isinstance(body_data_b64, str):
            try:
                self._decoded_body_cache = base64.b64decode(body_data_b64)
                return self._decoded_body_cache
            except Exception:
                return None  # Or log error
        return None

    @property
    def text(self) -> Optional[str]:
        decoded_bytes = self._get_decoded_body()
        if decoded_bytes is None:
            return None

        # Try to determine encoding from Content-Type header
        # This is a simplified approach. A more robust one would parse Content-Type fully.
        content_type_header = self._parent_entry.response.headers.get(
            "Content-Type", ""
        ).lower()
        encoding = "utf-8"  # Default encoding
        if "charset=" in content_type_header:
            try:
                encoding = (
                    content_type_header.split("charset=")[-1].split(";")[0].strip()
                )
            except IndexError:
                pass  # Stick to default if charset parsing fails

        try:
            return decoded_bytes.decode(encoding, errors="replace")
        except LookupError:  # Unknown encoding
            try:
                return decoded_bytes.decode(
                    "utf-8", errors="replace"
                )  # Fallback to utf-8
            except Exception:
                return None
        except Exception:
            return None  # Other decoding errors

    @property
    def raw_size(self) -> Optional[int]:
        # Proxyman provides 'bodySize' for raw (uncompressed) size
        # and 'bodyEncodedSize' for transferred (potentially compressed) size.
        # The `bodyData` when decoded is the raw content.
        decoded_body = self._get_decoded_body()
        return (
            len(decoded_body)
            if decoded_body is not None
            else self._data.get("bodySize")
        )  # Prefer actual len, fallback to header

    @property
    def compressed_size(self) -> Optional[int]:
        # This corresponds to the size of 'bodyData' if it were not base64 encoded,
        # or directly 'bodyEncodedSize' if available. If bodyData is present,
        # its length is base64 encoded. Original compressed is in 'bodyEncodedSize'.
        size = self._data.get("bodyEncodedSize")
        if size is not None:
            return int(size)

        # Fallback: if bodyData is present, its length after base64 encoding is a rough proxy
        # but it's not the true compressed size on the wire. Proxyman usually provides bodyEncodedSize.
        # body_data_b64 = self._data.get("bodyData")
        # if body_data_b64 and isinstance(body_data_b64, str):
        #     return len(body_data_b64) # This is base64 encoded length, not true compressed size
        return self.raw_size  # If no better info, assume not compressed or info missing


class _ProxymanResponseDetails(ResponseDetails):
    """Implementation of ResponseDetails for a Proxyman entry."""

    def __init__(self, entry_data: Dict[str, Any], parent_entry: "ProxymanLogV2Entry"):
        self._data = entry_data.get("response", {})
        self._parent_entry = parent_entry
        self._body_details = _ProxymanResponseBodyDetails(entry_data, parent_entry)

    @property
    def headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {}
        header_entries: List[Dict[str, Any]] = self._data.get("header", {}).get(
            "entries", []
        )
        for entry in header_entries:
            key_info = entry.get("key", {})
            key_name = key_info.get("name")
            value = entry.get("value")
            if key_name is not None and value is not None:
                hdrs[str(key_name)] = str(value)
        return hdrs

    @property
    def mime_type(self) -> Optional[str]:
        ct = self.content_type
        return ct.split(";")[0].strip() if ct else None

    @property
    def content_type(self) -> Optional[str]:
        # Proxyman response headers are parsed by .headers property
        # Content-Type is a standard header name
        return self.headers.get(
            "Content-Type"
        )  # Case-sensitive match as dict keys are exact
        # For case-insensitive, iterate self.headers.items()

    @property
    def body(self) -> ResponseBodyDetails:
        return self._body_details

    @property
    def status_code(self) -> int:
        return self._data.get("status", {}).get("code", 0)  # Default to 0 if not found


class _ProxymanTimelineDetails(TimelineDetails):
    """Implementation of TimelineDetails for a Proxyman entry."""

    def __init__(self, entry_data: Dict[str, Any]):
        self._data = entry_data.get("timing", {})

    @property
    def request_start(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self._data.get("requestStartedAt", 0))

    @property
    def request_end(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self._data.get("requestEndedAt", 0))

    @property
    def response_start(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self._data.get("responseStartedAt", 0))

    @property
    def response_end(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self._data.get("responseEndedAt", 0))


class ProxymanLogV2Entry(TraceEntry):
    """
    Represents a single request/response entry from a Proxyman log file.
    This class provides access to entry data according to the CaptureEntry interface.
    Lazy loading is employed for potentially large data like response bodies.
    """

    def __init__(
        self, entry_name: str, raw_data: Dict[str, Any], reader: Any
    ):  # 'reader' type hint as 'ProxymanLogV2Reader' causes circularity if not careful
        """
        Initializes the entry with its raw JSON data and a reference to the reader.

        Args:
            entry_name: The internal filename or identifier for this entry in the archive.
            raw_data: The dictionary containing the parsed JSON content of the entry.
            reader: The ProxymanLogV2Reader instance that this entry belongs to.
        """
        self._entry_name = entry_name
        self._raw_data = raw_data
        self._reader = reader

        # Use functools.cached_property for lazy initialization of detail objects
        # This is an alternative to initializing all in __init__
        # For simplicity, we'll initialize them here, but cached_property is good for performance.

        self._request = _ProxymanRequestDetails(self._raw_data, self)
        self._response = _ProxymanResponseDetails(self._raw_data, self)
        self._timeline = _ProxymanTimelineDetails(self._raw_data)

    @property
    def index(self) -> int:
        """
        The numerical index of the entry, parsed from its filename.
        e.g., 'request_123_abc' -> 123. Returns -1 if parsing fails.
        """
        try:
            # Assumes format "request_INDEX_ID"
            return int(self._entry_name.split("_")[1])
        except (IndexError, ValueError):
            # Fallback for unexpected filename format
            # Try to get from the reader's index if available and reliable
            if self._reader and hasattr(self._reader, "_index"):
                return self._reader._index.get(self._entry_name, {}).get("index", -1)
            return -1

    @property
    def id(self) -> str:
        """
        The unique identifier of the entry, typically part of the filename.
        e.g., 'request_123_abc' -> 'abc'. Also available as 'id' in raw data.
        """
        # The 'id' field in the JSON is the most reliable source
        explicit_id = self._raw_data.get("id")
        if explicit_id:
            return str(explicit_id)

        # Fallback to parsing from the filename
        try:
            # Assumes format "request_INDEX_ID"
            return self._entry_name.split("_")[2]
        except IndexError:
            # If all else fails, return the entry name itself as a unique-ish ID
            return self._entry_name

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
        # Proxyman stores comments in style.comment
        style = self._raw_data.get("style", {})
        if isinstance(style, dict):
            comment = style.get("comment")
            if comment:
                return comment
        # Fallback to 'notes' for backward compatibility with older files
        return self._raw_data.get("notes")

    @property
    def highlight(self) -> Optional[str]:
        """An optional highlight style for the entry."""
        style = self._raw_data.get("style", {})
        if isinstance(style, dict):
            # Check for strike-through first
            if "textStyle" in style and style.get("textStyle") == 0:
                return "strike"
            # Check for color
            if "color" in style:
                color_int = style["color"]
                # Convert color int back to string
                for color_name, color_val in HIGHLIGHT_COLOR_MAP.items():
                    if color_val == color_int:
                        return color_name
        return None

    @property
    def timeline(self) -> TimelineDetails:
        """Timeline details of the HTTP exchange."""
        return self._timeline

    # --- Additional Proxyman-specific methods ---

    def get_raw_json(self) -> Dict[str, Any]:
        """Returns the raw, unmodified JSON data for this entry."""
        return self._raw_data

    def set_comment(self, comment: str) -> None:
        """
        Set a comment/note on this entry.

        Args:
            comment: The comment text to add to this entry.
        """
        if "style" not in self._raw_data:
            self._raw_data["style"] = {}
        self._raw_data["style"]["comment"] = comment

    def add_response_header(self, name: str, value: str) -> None:
        """
        Add or update a header in the response.

        If a header with the same name already exists, its value will be updated.
        Otherwise, a new header will be added.

        Args:
            name: The header name.
            value: The header value.
        """
        if "response" not in self._raw_data:
            self._raw_data["response"] = {}
        if "header" not in self._raw_data["response"]:
            self._raw_data["response"]["header"] = {"entries": []}

        entries = self._raw_data["response"]["header"]["entries"]
        # Check if header already exists and update it
        for entry in entries:
            if entry.get("key", {}).get("name") == name:
                entry["value"] = value
                return
        # Add new header if it doesn't exist
        entries.append({"key": {"name": name}, "value": value})

    def add_request_header(self, name: str, value: str) -> None:
        """
        Add or update a header in the request.

        If a header with the same name already exists, its value will be updated.
        Otherwise, a new header will be added.

        Args:
            name: The header name.
            value: The header value.
        """
        if "request" not in self._raw_data:
            self._raw_data["request"] = {}
        if "header" not in self._raw_data["request"]:
            self._raw_data["request"]["header"] = {"entries": []}

        entries = self._raw_data["request"]["header"]["entries"]
        # Check if header already exists and update it
        for entry in entries:
            if entry.get("key", {}).get("name") == name:
                entry["value"] = value
                return
        # Add new header if it doesn't exist
        entries.append({"key": {"name": name}, "value": value})

    def set_highlight(self, highlight: str) -> None:
        """
        Set a highlight color or strike-through style on this entry.

        Supported values:
        - "red" (0)
        - "yellow" (1)
        - "green" (2)
        - "blue" (3)
        - "purple" (4)
        - "grey" (5)
        - "strike" (sets textStyle to 0)

        Args:
            highlight: The highlight style to apply.

        Raises:
            ValueError: If an invalid highlight value is provided.
        """
        validate_highlight(highlight)

        if "style" not in self._raw_data:
            self._raw_data["style"] = {}

        if highlight == "strike":
            # Set textStyle to 0 for strike-through
            self._raw_data["style"]["textStyle"] = 0
            # Remove color if it exists
            if "color" in self._raw_data["style"]:
                del self._raw_data["style"]["color"]
        elif highlight in HIGHLIGHT_COLOR_MAP:
            # Set color value
            self._raw_data["style"]["color"] = HIGHLIGHT_COLOR_MAP[highlight]
            # Remove textStyle if it exists
            if "textStyle" in self._raw_data["style"]:
                del self._raw_data["style"]["textStyle"]

    def __str__(self) -> str:
        """Provides a user-friendly string representation."""
        return f"ProxymanLogV2Entry(id={self.id} {self.request.method} {self.request.url} -> {self.response.status_code})"

    def __repr__(self) -> str:
        """
        Provides a detailed, unambiguous string representation for developers.
        """
        return f"<ProxymanLogV2Entry id={self.id} {self.request.method} {self.request.url} -> {self.response.status_code}>"

    @classmethod
    def from_trace_entry(
        cls, entry: TraceEntry, index: int = 0
    ) -> Tuple[Dict[str, Any], str]:
        """
        Create a Proxyman entry dictionary and filename from a TraceEntry.

        Args:
            entry: The TraceEntry to convert.
            index: The index of the entry (used in filename).

        Returns:
            Tuple of (entry_data_dict, filename).
        """
        timeline = entry.timeline
        url = entry.request.url

        # Parse URL components
        scheme = url.scheme or "http"
        host = url.host or ""
        port = url.port
        uri = url.path_qs

        # Build request headers
        request_header_entries = [
            {
                "key": {"name": name, "nameInLowercase": name.lower()},
                "value": value,
                "isEnabled": True,
            }
            for name, value in entry.request.headers.items()
        ]

        # Build request object
        request_obj: Dict[str, Any] = {
            "host": host,
            "port": port if port else (443 if scheme == "https" else 80),
            "isSSL": scheme == "https",
            "method": {"name": entry.request.method},
            "scheme": scheme,
            "fullPath": str(url),
            "uri": uri,
            "version": {"major": 1, "minor": 1},
            "header": {"entries": request_header_entries},
            "bodyData": "",
            "compressedBodyDataCount": 0,
            "isWebSocketUpgrade": False,
        }

        # Build response headers
        response_header_entries = [
            {
                "key": {"name": name, "nameInLowercase": name.lower()},
                "value": value,
                "isEnabled": True,
            }
            for name, value in entry.response.headers.items()
        ]

        # Build response body
        response_body = entry.response.body
        body_size = response_body.raw_size or 0
        body_encoded_size = response_body.compressed_size or body_size

        body_data_b64 = ""
        try:
            content = entry.content
            if isinstance(content, bytes):
                body_data_b64 = base64.b64encode(content).decode("utf-8")
            elif isinstance(content, str):
                body_data_b64 = base64.b64encode(content.encode("utf-8")).decode(
                    "utf-8"
                )
        except Exception:
            if response_body.text is not None:
                try:
                    body_data_b64 = base64.b64encode(
                        response_body.text.encode("utf-8")
                    ).decode("utf-8")
                except Exception:
                    pass

        # Build response object
        response_obj: Dict[str, Any] = {
            "status": {
                "code": entry.response.status_code,
                "phrase": cls._get_status_text(entry.response.status_code),
                "strict": False,
            },
            "version": {"major": 1, "minor": 1},
            "header": {"entries": response_header_entries},
            "bodyData": body_data_b64,
            "bodySize": body_size,
            "bodyEncodedSize": body_encoded_size,
            "compressedBodyDataCount": body_encoded_size,
            "createdAt": (
                timeline.response_end.timestamp()
                if timeline.response_end
                else datetime.now().timestamp()
            ),
            "error": None,
        }

        # Build timing object
        timing_obj: Dict[str, float] = {}
        if timeline.request_start:
            timing_obj["requestStartedAt"] = timeline.request_start.timestamp()

        # Safely get request_end (may raise NotImplementedError for HAR entries)
        try:
            request_end = timeline.request_end
            if request_end:
                timing_obj["requestEndedAt"] = request_end.timestamp()
        except NotImplementedError:
            pass

        # Safely get response_start (may raise NotImplementedError for HAR entries)
        try:
            response_start = timeline.response_start
            if response_start:
                timing_obj["responseStartedAt"] = response_start.timestamp()
        except NotImplementedError:
            pass

        if timeline.response_end:
            timing_obj["responseEndedAt"] = timeline.response_end.timestamp()

        # Build entry ID
        entry_id = entry.id
        if entry_id.startswith("index-"):
            entry_id = f"entry_{index}"

        # Build the complete entry
        proxyman_entry: Dict[str, Any] = {
            "id": entry_id,
            "name": entry_id,
            "request": request_obj,
            "response": response_obj,
            "timing": timing_obj,
            "isSSL": scheme == "https",
            "isIntercepted": True,
            "isRelayed": False,
            "isFromFile": False,
            "timezone": "GMT",
        }

        # Handle comment
        if entry.comment:
            proxyman_entry["style"] = proxyman_entry.get("style", {})
            proxyman_entry["style"]["comment"] = entry.comment

        # Handle highlight
        if entry.highlight:
            highlight = entry.highlight
            proxyman_entry["style"] = proxyman_entry.get("style", {})
            if highlight == "strike":
                proxyman_entry["style"]["textStyle"] = 0
                if "color" in proxyman_entry["style"]:
                    del proxyman_entry["style"]["color"]
            elif highlight in HIGHLIGHT_COLOR_MAP:
                proxyman_entry["style"]["color"] = HIGHLIGHT_COLOR_MAP[highlight]
                if "textStyle" in proxyman_entry["style"]:
                    del proxyman_entry["style"]["textStyle"]

        filename = f"request_{index}_{entry_id}"

        return proxyman_entry, filename

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
