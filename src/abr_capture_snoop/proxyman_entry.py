import base64
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from yarl import URL

from .capture_entry import (
    CaptureEntry,
    RequestDetails,
    ResponseBodyDetails,
    ResponseDetails,
    TimingsDetails,
)

# Forward declaration for type hinting reader if ProxymanLogV2Reader is in a separate file
# from .proxyman_log_reader import ProxymanLogV2Reader # Causes circular import if in same file or __init__

# --- Helper classes for ProxymanLogV2Entry ---


class _ProxymanRequestDetails(RequestDetails):
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


class _ProxymanTimingsDetails(TimingsDetails):
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


class ProxymanLogV2Entry(CaptureEntry):
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
            reader: The ProxymanLogV2Reader instance that loaded this entry.
        """
        if not isinstance(raw_data, dict):
            raise TypeError("raw_data must be a dictionary")

        self._entry_name = entry_name
        self._raw_data = raw_data
        self._reader = reader  # Store reader reference if needed later (e.g. for re-fetching parts)

        # Initialize helper objects that parse parts of raw_data
        self._request_details = _ProxymanRequestDetails(self._raw_data, self)
        self._response_details = _ProxymanResponseDetails(self._raw_data, self)
        self._timing_details = _ProxymanTimingsDetails(
            self._raw_data
        )  # Pass raw_data directly

    @property
    def index(self) -> int:
        """Returns the numerical index of the entry, parsed from its filename."""
        # entry_filename is like 'request_INDEX_TRACERID' (e.g., 'request_0_abc-123')
        parts = self._entry_name.split("_")
        if len(parts) > 1 and parts[0] == "request" and parts[1].isdigit():
            return int(parts[1])
        # Fallback or error if pattern doesn't match - though reader should ensure correct names.
        # For safety, return a default or raise an error if parsing fails unexpectedly.
        # However, given the context of how entry_filename is generated by the reader,
        # this parse should be quite robust.
        # If _entry_name is not guaranteed, a more complex regex might be needed.
        # For now, assume the pattern from ProxymanLogV2Reader is consistent.
        # Consider raising ValueError if parsing fails, to highlight issues.
        # Or, if the reader guarantees the format, direct parsing is fine.
        # Let's make it robust to at least not crash if the format is weird.
        try:
            # Attempt to extract the index, default to -1 or raise if critical
            # request_0_id -> 0
            # request_123_id -> 123
            return int(self._entry_name.split("_")[1])
        except (IndexError, ValueError):
            # This case should ideally not be reached if entry names are consistent
            # from the reader.
            # Consider logging a warning or returning a sentinel like -1.
            # For now, returning -1 for robustness in tests if somehow an odd name gets through.
            # In a real scenario, this might indicate an issue with how entry_name was formed.
            return (
                -1
            )  # Should be discussed what a sensible default is, or if it should raise

    @property
    def id(self) -> str:
        """Returns the unique ID of the entry (e.g., '123' from 'request_0_123')."""
        # Proxyman JSON has an 'id' field at the top level, e.g., "id": "m1ysg8"
        # It also has an id in the filename like request_INDEX_TRACERID (e.g. request_0_abc-123)
        # The self._entry_name is like 'request_0_abc-123' from the reader
        # The self._raw_data.get("id") is a different UUID-like ID.
        # Let's use the Proxyman top-level 'id' if available, otherwise fallback to one from filename.
        internal_proxyman_id = self._raw_data.get("id")
        if internal_proxyman_id:
            return str(internal_proxyman_id)

        # Fallback to extracting from entry_name (e.g., 'request_0_my-id-123' -> 'my-id-123')
        parts = self._entry_name.split("_")
        if len(parts) > 2:
            return parts[-1]  # The part after the last underscore
        return self._entry_name  # Fallback to the full entry name if parsing fails

    @property
    def request(self) -> RequestDetails:
        return self._request_details

    @property
    def response(self) -> ResponseDetails:
        return self._response_details

    @property
    def comment(self) -> Optional[str]:
        # Proxyman doesn't have a standard 'comment' field per entry in the JSON structure.
        # It has a 'notes' field which might be user-added.
        return self._raw_data.get("notes")  # Or None if 'notes' is not present

    @property
    def timings(self) -> TimingsDetails:
        return self._timing_details

    # --- Potentially useful additional methods specific to Proxyman data structure ---

    def get_raw_json(self) -> Dict[str, Any]:
        """Returns the original raw JSON data for this entry."""
        return self._raw_data

    def __str__(self) -> str:
        method = self.request.method
        url_str = str(self.request.url)
        status = self.response.status_code
        return f"ProxymanLogV2Entry({self.id} {method} {url_str} -> {status})"

    def __repr__(self) -> str:
        return f"<ProxymanLogV2Entry id={self.id} url={str(self.request.url)}>"
