from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union  # Add yarl.URL later

# from yarl import URL # Will uncomment once yarl is used


class RequestDetails(ABC):
    @property
    @abstractmethod
    def url(self) -> Any:  # yarl.URL:
        pass

    @property
    @abstractmethod
    def headers(self) -> Dict[str, str]:
        pass

    @property
    @abstractmethod
    def method(self) -> str:
        pass

    @property
    @abstractmethod
    def body(self) -> Optional[bytes]:  # Or stream, or helper methods
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


class TimingsDetails(ABC):
    # Define specific timing properties later based on commonalities
    # e.g., connect_time, send_time, wait_time, receive_time
    # Need to consider timezone handling
    pass


class CaptureEntry(ABC):
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
    def timings(self) -> TimingsDetails:  # Or specific timing attributes directly
        pass
