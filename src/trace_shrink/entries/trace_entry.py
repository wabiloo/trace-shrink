from datetime import datetime
from typing import Dict, Optional

import yarl

from ..utils.formats import Format, MimeType
from ..utils.highlight import validate_highlight


class RequestDetails:
    """Concrete class for details of an HTTP request."""

    def __init__(
        self,
        url: yarl.URL,
        method: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
    ):
        self._url = url
        self._method = method
        self._headers = headers.copy()
        self._body = body

    @property
    def url(self) -> yarl.URL:
        """The URL of the request."""
        return self._url

    @property
    def headers(self) -> Dict[str, str]:
        """A dictionary of request headers."""
        return self._headers.copy()

    @property
    def method(self) -> str:
        """The HTTP method (e.g., 'GET', 'POST')."""
        return self._method

    @property
    def body(self) -> Optional[bytes]:
        """The request body, if available."""
        return self._body


class ResponseBodyDetails:
    """Concrete class for details of an HTTP response body."""

    def __init__(
        self,
        text: Optional[str] = None,
        raw_size: Optional[int] = None,
        compressed_size: Optional[int] = None,
        decoded_body: Optional[bytes] = None,
    ):
        self._text = text
        self._raw_size = raw_size
        self._compressed_size = compressed_size
        self._decoded_body = decoded_body

    def _get_decoded_body(self) -> Optional[bytes]:
        """Get the decoded body as bytes."""
        if self._decoded_body is not None:
            return self._decoded_body
        if self._text is not None:
            return self._text.encode("utf-8")
        return None

    @property
    def text(self) -> Optional[str]:
        """The textual content of the response body, if available."""
        return self._text

    @property
    def raw_size(self) -> Optional[int]:
        """The raw size of the response body in bytes."""
        return self._raw_size

    @property
    def compressed_size(self) -> Optional[int]:
        """The compressed (transfer) size of the response body in bytes."""
        return self._compressed_size


class ResponseDetails:
    """Concrete class for details of an HTTP response."""

    def __init__(
        self,
        headers: Dict[str, str],
        status_code: int,
        mime_type: Optional[str] = None,
        content_type: Optional[str] = None,
        body: Optional[ResponseBodyDetails] = None,
    ):
        self._headers = headers.copy()
        self._status_code = status_code
        self._mime_type = mime_type
        self._content_type = content_type or mime_type
        self._body = body or ResponseBodyDetails()

    @property
    def headers(self) -> Dict[str, str]:
        """A dictionary of response headers."""
        return self._headers.copy()

    @property
    def mime_type(self) -> Optional[str]:
        """The MIME type of the response."""
        return self._mime_type

    @property
    def content_type(self) -> Optional[str]:
        """The content type of the response."""
        return self._content_type

    @property
    def body(self) -> ResponseBodyDetails:
        """Details of the response body."""
        return self._body

    @property
    def status_code(self) -> int:
        """The HTTP status code of the response."""
        return self._status_code


class TimelineDetails:
    """Concrete class for timeline details of an HTTP exchange."""

    def __init__(
        self,
        request_start: Optional[datetime] = None,
        request_end: Optional[datetime] = None,
        response_start: Optional[datetime] = None,
        response_end: Optional[datetime] = None,
    ):
        self._request_start = request_start
        self._request_end = request_end
        self._response_start = response_start
        self._response_end = response_end

    @property
    def request_start(self) -> Optional[datetime]:
        """The start time of the request."""
        return self._request_start

    @property
    def request_end(self) -> Optional[datetime]:
        """The end time of the request."""
        return self._request_end

    @property
    def response_start(self) -> Optional[datetime]:
        """The start time of the response."""
        return self._response_start

    @property
    def response_end(self) -> Optional[datetime]:
        """The end time of the response."""
        return self._response_end


class MergedResponseDetails(ResponseDetails):
    """ResponseDetails wrapper that merges original headers with overrides."""

    def __init__(
        self,
        original: ResponseDetails,
        override_headers: Dict[str, str],
    ):
        # Merge headers: overrides take precedence
        merged_headers = original.headers.copy()
        merged_headers.update(override_headers)

        super().__init__(
            headers=merged_headers,
            status_code=original.status_code,
            mime_type=original.mime_type,
            content_type=original.content_type,
            body=original.body,
        )


class TraceEntry:
    """Concrete model class for a single entry in a trace archive."""

    def __init__(
        self,
        index: int,
        entry_id: str,
        request: RequestDetails,
        response: ResponseDetails,
        timeline: TimelineDetails,
        comment: Optional[str] = None,
        highlight: Optional[str] = None,
        annotations: Optional[Dict[str, str]] = None,
    ):
        self._index = index
        self._id = entry_id
        self._request = request
        self._response = response
        self._timeline = timeline
        self._comment = comment
        self._highlight = highlight
        self._annotations = annotations or {}

        # Override storage for mutations
        self._override_comment: Optional[str] = None
        self._override_highlight: Optional[str] = None
        self._override_request_headers: Dict[str, str] = {}
        self._override_response_headers: Dict[str, str] = {}
        self._override_response_content: Optional[str] = None
        self._override_annotations: Dict[str, str] = {}

    @property
    def index(self) -> int:
        """The zero-based index of the entry in the archive."""
        return self._index

    @property
    def id(self) -> str:
        """A unique identifier for the entry."""
        return self._id

    @property
    def request(self) -> RequestDetails:
        """Details of the HTTP request, with merged override headers."""
        if self._override_request_headers:
            # Create a new RequestDetails with merged headers
            merged_headers = self._request.headers.copy()
            merged_headers.update(self._override_request_headers)
            return RequestDetails(
                url=self._request.url,
                method=self._request.method,
                headers=merged_headers,
                body=self._request.body,
            )
        return self._request

    @property
    def response(self) -> ResponseDetails:
        """Details of the HTTP response, with merged override headers."""
        if self._override_response_headers:
            return MergedResponseDetails(
                self._response, self._override_response_headers
            )
        return self._response

    @property
    def timeline(self) -> TimelineDetails:
        """Timeline details of the HTTP exchange."""
        return self._timeline

    @property
    def comment(self) -> Optional[str]:
        """An optional comment for the entry."""
        return (
            self._override_comment
            if self._override_comment is not None
            else self._comment
        )

    @property
    def highlight(self) -> Optional[str]:
        """An optional highlight style for the entry (e.g., 'red', 'yellow', 'strike')."""
        return (
            self._override_highlight
            if self._override_highlight is not None
            else self._highlight
        )

    def set_comment(self, comment: str) -> None:
        """Set a comment on this entry."""
        self._override_comment = comment

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

        Args:
            highlight: The highlight style to apply.

        Raises:
            ValueError: If an invalid highlight value is provided.
        """
        validate_highlight(highlight)
        self._override_highlight = highlight

    def add_request_header(self, name: str, value: str) -> None:
        """Add or update a header in the request."""
        self._override_request_headers[name] = value

    def add_response_header(self, name: str, value: str) -> None:
        """Add or update a header in the response."""
        self._override_response_headers[name] = value

    def set_response_content(self, content: str) -> None:
        """Set the response body content."""
        self._override_response_content = content

    @property
    def annotations(self) -> Dict[str, str]:
        """Return annotations dict, merging overrides with original annotations.

        Filters out None values (which represent removed annotations).
        """
        merged = dict(self._annotations)
        # Update with overrides, filtering out None values (removed annotations)
        for key, value in self._override_annotations.items():
            if value is None:
                # Remove annotation if it was marked as None
                merged.pop(key, None)
            else:
                merged[key] = value
        return merged

    def add_annotation(self, annotation_type: str, content: str) -> None:
        """Add or update an annotation.

        Args:
            annotation_type: The type/key of the annotation (e.g., "digest", "dash-preview")
            content: The annotation content/value
        """
        self._override_annotations[annotation_type] = content

    def remove_annotation(self, annotation_type: str) -> None:
        """Remove an annotation.

        Args:
            annotation_type: The type/key of the annotation to remove
        """
        # Mark as removed by setting to None in overrides
        self._override_annotations[annotation_type] = None

    @property
    def content(self) -> bytes | str:
        """The content of the entry, extracted from the response body."""
        # Check override first
        if self._override_response_content is not None:
            return self._override_response_content

        # Fall back to reading from response body
        body = self.response.body

        # Check if content_type indicates text content
        content_type = self.response.content_type
        if content_type:
            try:
                if MimeType(content_type).has_text_content():
                    return body.text or ""
            except ValueError:
                # Invalid mime type, treat as binary
                pass

        # Default to binary/bytes
        decoded = body._get_decoded_body()
        return decoded if decoded is not None else b""

    @property
    def content_bytes(self) -> bytes:
        """The content of the entry as bytes, converting strings if necessary."""
        content = self.content
        if isinstance(content, bytes):
            return content
        elif isinstance(content, str):
            return content.encode("utf-8")
        else:
            return b""

    @property
    def format(self) -> Optional[Format]:
        """The format of the entry (HLS, DASH, or None), determined from content type or URL."""
        mime_type = self.response.content_type or self.response.mime_type
        if mime_type:
            try:
                return Format.from_url_or_mime_type(mime_type, self.request.url)
            except ValueError:
                pass
        return Format.from_url(self.request.url)

    def __str__(self) -> str:
        """String representation of the entry."""
        return (
            f"TraceEntry(id={self.id} {self.request.method} "
            f"{self.request.url} -> {self.response.status_code})"
        )

    def __repr__(self) -> str:
        """Detailed string representation of the entry."""
        return (
            f"<TraceEntry id={self.id} {self.request.method} "
            f"{self.request.url} -> {self.response.status_code}>"
        )
