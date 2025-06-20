import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yarl

from .formats import Format
from .manifest_stream import ManifestStream
from .trace_entry import TraceEntry


@dataclass
class DecoratedUrl:
    url: yarl.URL
    format: str

    def __hash__(self) -> int:
        return hash((self.url, self.format))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DecoratedUrl):
            return False
        return self.url == other.url and self.format == other.format


class ArchiveReader(ABC):
    """
    Abstract base class for all trace archive readers (HAR, Proxyman, etc).

    To instantiate the correct reader for a given file, use the
    `open_archive(path)` factory function provided by the package.
    """

    def __init__(self):
        self._url_index: Optional[Dict[str, List[TraceEntry]]] = None
        self._path_index: Optional[Dict[str, List[TraceEntry]]] = None

    @property
    @abstractmethod
    def entries(self) -> List[TraceEntry]:
        """
        Returns a list of entries.
        """
        pass

    @abstractmethod
    def __len__(self) -> int:
        """
        Returns the number of entries in the archive.
        """
        pass

    @abstractmethod
    def __iter__(self) -> Iterator[TraceEntry]:
        """
        Returns an iterator over the entries in the archive.
        """
        pass

    def _build_url_index(self) -> Dict[str, List[TraceEntry]]:
        """
        Builds an index mapping URLs to entries for fast lookups.
        This is cached after the first call.
        """
        if self._url_index is None:
            self._url_index = {}
            for entry in self.entries:
                url_str = str(entry.request.url)
                if url_str not in self._url_index:
                    self._url_index[url_str] = []
                self._url_index[url_str].append(entry)
        return self._url_index

    def _build_path_index(self) -> Dict[str, List[TraceEntry]]:
        """
        Builds an index mapping URL paths to entries for fast lookups.
        This is cached after the first call.
        """
        if self._path_index is None:
            self._path_index = {}
            for entry in self.entries:
                path = entry.request.url.path
                if path not in self._path_index:
                    self._path_index[path] = []
                self._path_index[path].append(entry)
        return self._path_index

    def get_entries_for_url(self, url: str | yarl.URL) -> List[TraceEntry]:
        """
        Retrieves entries for a specific URL using a fast indexed lookup.
        """
        url_index = self._build_url_index()
        return url_index.get(str(url), [])

    def get_entries_by_path(self, path: str) -> List[TraceEntry]:
        """
        Retrieves entries for a specific path using a fast indexed lookup.
        """
        path_index = self._build_path_index()
        return path_index.get(path, [])

    def get_entries_for_partial_url(
        self, url_pattern: str | re.Pattern
    ) -> List[TraceEntry]:
        """
        Retrieves entries whose request URL matches the given pattern.
        Uses optimized searching when possible.
        """
        matching_entries: List[TraceEntry] = []

        if isinstance(url_pattern, re.Pattern):
            # For regex patterns, we need to scan all URLs
            url_index = self._build_url_index()
            for url_str, entries in url_index.items():
                if url_pattern.search(url_str):
                    matching_entries.extend(entries)
        else:
            # For string patterns, we can optimize by scanning the index keys first
            url_index = self._build_url_index()
            for url_str, entries in url_index.items():
                if url_pattern in url_str:
                    matching_entries.extend(entries)

        return matching_entries

    def filter(
        self,
        host: Optional[str] = None,
        url: Optional[str] = None,
        partial_url: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> List[TraceEntry]:
        """
        Filters entries based on a set of optional criteria.

        This implementation relies on the following attributes of CaptureEntry and its nested objects:
        - entry.request.url: (string-like or yarl.URL) for the full request URL.
        - entry.response.mime_type: str for the response MIME type.

        Filtering by start_time and end_time is temporarily removed as the specific
        timing attributes are not yet defined in CaptureEntry or its TimingsDetails.

        Args:
            host: If provided, only entries with a matching request host are returned.
            url: If provided, only entries with an exact matching request URL are returned.
            partial_url: If provided, only entries whose request URL contains this string are returned.
            mime_type: If provided, only entries with a matching response MIME type are returned.

        Returns:
            A list of CaptureEntry objects that satisfy all provided filter criteria.
        """
        filtered_entries: List[TraceEntry] = []
        for entry in self.entries:
            # Host filter
            if host is not None:
                try:
                    entry_host = urlparse(
                        str(entry.request.url)
                    ).hostname  # Ensure entry.request.url is stringifiable
                    if entry_host != host:
                        continue
                except (AttributeError, TypeError):
                    # AttributeError: if entry.request or entry.request.url is missing
                    # TypeError: if str(entry.request.url) fails or urlparse fails
                    continue

            # Full URL filter
            if url is not None:
                try:
                    if str(entry.request.url) != url:
                        continue
                except (AttributeError, TypeError):
                    continue

            # Partial URL filter
            if partial_url is not None:
                try:
                    if partial_url not in str(entry.request.url):
                        continue
                except (AttributeError, TypeError):
                    continue

            # MIME type filter
            if mime_type is not None:
                try:
                    if entry.response.mime_type != mime_type:
                        continue
                except (AttributeError, TypeError):
                    # AttributeError: if entry.response or entry.response.mime_type is missing
                    # TypeError: if entry.response.mime_type is not comparable
                    continue

            # NOTE: Time-based filtering (start_time, end_time) will be added here
            # once CaptureEntry.timings exposes the necessary attributes.

            filtered_entries.append(entry)
        return filtered_entries

    def get_manifest_stream(self, manifest_url: str | yarl.URL) -> ManifestStream:
        """
        Filters entries for the given manifest_url and returns a
        ManifestStream object to manage them.

        Args:
            manifest_url: The URL of the manifest to get a stream for.

        Returns:
            A ManifestStream object.

        Raises:
            ValueError: If no entries are found for the given manifest URL.
        """
        manifest_entries = self.get_entries_for_url(manifest_url)
        if not manifest_entries:
            raise ValueError(f"No entries found for manifest URL: {manifest_url}")
        return ManifestStream(manifest_entries)

    # ==== ABR manifest URLs ====

    def get_abr_manifest_urls(
        self, format: Optional[str | Format] = None
    ) -> List[DecoratedUrl]:
        """
        Retrieves a list of URLs for ABR manifests, with optional filtering by format.
        """
        if isinstance(format, str):
            format = Format(format)
        urls = []
        for entry in self.entries:
            abr_format = Format.from_url_or_mime_type(
                entry.response.mime_type, entry.request.url
            )
            if abr_format is None:
                continue
            if format is not None and abr_format != format:
                continue
            urls.append(DecoratedUrl(entry.request.url, abr_format.value))
        return list(set(urls))
