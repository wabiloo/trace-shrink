from abc import ABC, abstractmethod
from typing import List

from abr_capture_snoop.capture_entry import CaptureEntry


class ArchiveReader(ABC):
    @property
    @abstractmethod
    def entries(self) -> List[CaptureEntry]:
        """
        Returns a list of entries.
        """
        pass

    @abstractmethod
    def get_entries_for_url(self, url_pattern: str) -> List[CaptureEntry]:
        """
        Retrieves entries whose request URL matches the given pattern.
        """
        pass

    # Other common methods might be added later
