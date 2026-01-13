from abc import ABC
from collections.abc import Iterator
from typing import Dict, List, Optional, Pattern

import yarl

from .formats import Format
from .manifest_stream import ManifestStream
from .trace import DecoratedUrl, Trace
from .trace_entry import TraceEntry


class TraceReader(ABC):
    """
    Abstract base class for all trace readers (HAR, Proxyman, etc).

    To instantiate the correct reader for a given file, use the
    `open_trace(path)` factory function provided by the package.
    """

    def __init__(self, trace: Optional[Trace] = None):
        self._trace = trace or Trace()

    @property
    def trace(self) -> Trace:
        return self._trace

    @property
    def entries(self) -> List[TraceEntry]:
        return self._trace.entries

    def __len__(self) -> int:
        return len(self._trace)

    def __iter__(self) -> Iterator[TraceEntry]:
        return iter(self._trace)

    def get_entry_by_id(self, entry_id: str) -> Optional[TraceEntry]:
        return self._trace.get_entry_by_id(entry_id)

    @property
    def _id_index(self) -> Optional[Dict[str, TraceEntry]]:
        return self._trace._id_index

    def get_next_entry_by_id(
        self, entry_id: str, direction: int, n: int = 1
    ) -> Optional[TraceEntry]:
        entry = self.get_entry_by_id(entry_id)
        if entry is None:
            return None

        manifest_stream = self.get_manifest_stream(entry.request.url)
        return manifest_stream.get_relative_entry(entry, direction, n)

    def get_entries_for_url(self, url: str | yarl.URL) -> List[TraceEntry]:
        return self._trace.get_entries_for_url(url)

    def get_entries_by_path(self, path: str) -> List[TraceEntry]:
        return self._trace.get_entries_by_path(path)

    def get_entries_by_ids(self, entry_ids: List[str]) -> List[TraceEntry]:
        return self._trace.get_entries_by_ids(entry_ids)

    def get_entries_for_partial_url(
        self, url_pattern: str | Pattern[str]
    ) -> List[TraceEntry]:
        return self._trace.get_entries_for_partial_url(url_pattern)

    def filter(
        self,
        host: Optional[str] = None,
        url: Optional[str] = None,
        partial_url: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> List[TraceEntry]:
        return self._trace.filter(
            host=host, url=url, partial_url=partial_url, mime_type=mime_type
        )

    def get_manifest_stream(self, manifest_url: str | yarl.URL) -> ManifestStream:
        return self._trace.get_manifest_stream(manifest_url)

    def get_abr_manifest_urls(
        self, format: Optional[str | Format] = None
    ) -> List[DecoratedUrl]:
        return self._trace.get_abr_manifest_urls(format_filter=format)

