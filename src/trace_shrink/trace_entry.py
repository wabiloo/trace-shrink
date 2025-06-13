from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Union  # Add yarl.URL later

import yarl

from trace_shrink.formats import MimeType


class RequestDetails(ABC):
    """Abstract base class for details of an HTTP request."""

    @property
    @abstractmethod
    def url(self) -> yarl.URL:
        """The URL of the request."""
        pass

    @property
    @abstractmethod
    def headers(self) -> Dict[str, str]:
        """A dictionary of request headers."""
        pass

    @property
    @abstractmethod
    def method(self) -> str:
        """The HTTP method (e.g., 'GET', 'POST')."""
        pass


class ResponseBodyDetails(ABC):
    """Abstract base class for details of an HTTP response body."""

    @property
    @abstractmethod
    def text(self) -> Optional[str]:
        """The textual content of the response body, if available."""
        pass

    @property
    @abstractmethod
    def raw_size(self) -> Optional[int]:
        """The raw size of the response body in bytes."""
        pass

    @property
    @abstractmethod
    def compressed_size(self) -> Optional[int]:  # Transfer size
        """The compressed (transfer) size of the response body in bytes."""
        pass


class ResponseDetails(ABC):
    """Abstract base class for details of an HTTP response."""

    @property
    @abstractmethod
    def headers(self) -> Dict[str, str]:
        """A dictionary of response headers."""
        pass

    @property
    @abstractmethod
    def mime_type(self) -> Optional[str]:
        """The MIME type of the response."""
        pass

    @property
    @abstractmethod
    def content_type(self) -> Optional[str]:
        """The content type of the response."""
        pass

    @property
    @abstractmethod
    def body(self) -> ResponseBodyDetails:
        """Details of the response body."""
        pass

    @property
    @abstractmethod
    def status_code(self) -> int:
        """The HTTP status code of the response."""
        pass


class TimelineDetails(ABC):
    """Abstract base class for timeline details of an HTTP exchange."""

    @property
    @abstractmethod
    def request_start(self) -> Optional[datetime]:
        """The start time of the request."""
        pass

    @property
    @abstractmethod
    def request_end(self) -> Optional[datetime]:
        """The end time of the request."""
        pass

    @property
    @abstractmethod
    def response_start(self) -> Optional[datetime]:
        """The start time of the response."""
        pass

    @property
    @abstractmethod
    def response_end(self) -> Optional[datetime]:
        """The end time of the response."""
        pass


class TraceEntry(ABC):
    """Abstract base class for a single entry in a trace archive."""

    @property
    @abstractmethod
    def index(self) -> int:
        """The zero-based index of the entry in the archive."""
        pass

    @property
    @abstractmethod
    def id(self) -> str:
        """A unique identifier for the entry."""
        pass

    @property
    @abstractmethod
    def request(self) -> RequestDetails:
        """Details of the HTTP request."""
        pass

    @property
    @abstractmethod
    def response(self) -> ResponseDetails:
        """Details of the HTTP response."""
        pass

    @property
    @abstractmethod
    def comment(self) -> Optional[str]:
        """An optional comment for the entry."""
        pass

    @property
    @abstractmethod
    def timeline(self) -> TimelineDetails:  # Or specific timing attributes directly
        """Timeline details of the HTTP exchange."""
        pass

    @property
    def content(self) -> bytes | str:
        """The content of the entry, extracted from the response body."""
        b = self.response.body

        if MimeType(self.response.content_type).has_text_content():
            return b.text
        else:
            return b._get_decoded_body()
