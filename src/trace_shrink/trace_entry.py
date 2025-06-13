from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Union  # Add yarl.URL later

import yarl


class RequestDetails(ABC):
    @property
    @abstractmethod
    def url(self) -> yarl.URL:
        pass

    @property
    @abstractmethod
    def headers(self) -> Dict[str, str]:
        pass

    @property
    @abstractmethod
    def method(self) -> str:
        pass


class ResponseBodyDetails(ABC):
    @property
    @abstractmethod
    def text(self) -> Optional[str]:
        pass

    @property
    @abstractmethod
    def raw_size(self) -> Optional[int]:
        pass

    @property
    @abstractmethod
    def compressed_size(self) -> Optional[int]:  # Transfer size
        pass


class ResponseDetails(ABC):
    @property
    @abstractmethod
    def headers(self) -> Dict[str, str]:
        pass

    @property
    @abstractmethod
    def mime_type(self) -> Optional[str]:
        pass

    @property
    @abstractmethod
    def content_type(self) -> Optional[str]:
        pass

    @property
    @abstractmethod
    def body(self) -> ResponseBodyDetails:
        pass

    @property
    @abstractmethod
    def status_code(self) -> int:
        pass


class TimelineDetails(ABC):
    @property
    @abstractmethod
    def request_start(self) -> Optional[datetime]:
        pass

    @property
    @abstractmethod
    def request_end(self) -> Optional[datetime]:
        pass

    @property
    @abstractmethod
    def response_start(self) -> Optional[datetime]:
        pass

    @property
    @abstractmethod
    def response_end(self) -> Optional[datetime]:
        pass


class TraceEntry(ABC):
    @property
    @abstractmethod
    def index(self) -> int:
        pass

    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @property
    @abstractmethod
    def request(self) -> RequestDetails:
        pass

    @property
    @abstractmethod
    def response(self) -> ResponseDetails:
        pass

    @property
    @abstractmethod
    def comment(self) -> Optional[str]:
        pass

    @property
    @abstractmethod
    def timeline(self) -> TimelineDetails:  # Or specific timing attributes directly
        pass

    @property
    def content(self) -> bytes | str:
        """The content of the entry, extracted from the response body."""
        b = self.response.body

        if is_string_content(self.response.content_type):
            return b.text
        else:
            return b._get_decoded_body()
