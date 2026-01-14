from __future__ import annotations

import re
from typing import (Any, Dict, Iterable, Iterator, List, Optional, Pattern,
                    Sequence, Union)

import yarl

from .abr import AbrDetector, ManifestStream
from .entries.trace_entry import TraceEntry
from .utils.formats import Format


class Trace:
    """Canonical in-memory container that holds trace metadata and entries."""

    def __init__(
        self,
        entries: Optional[Sequence[TraceEntry]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.metadata: Dict[str, Any] = metadata or {}
        self._entries: List[TraceEntry] = list(entries) if entries else []
        self._url_index: Optional[Dict[str, List[TraceEntry]]] = None
        self._path_index: Optional[Dict[str, List[TraceEntry]]] = None
        self._id_index: Optional[Dict[str, TraceEntry]] = None
        self.abr_detector: AbrDetector = AbrDetector()

    @property
    def entries(self) -> List[TraceEntry]:
        return self._entries

    @property
    def path(self) -> Optional[str]:
        """The path to the trace file or directory."""
        return self.metadata.get("path")

    @property
    def format(self) -> Optional[str]:
        """The format of the trace file: 'har', 'proxymanlogv2', 'bodylogger', or 'multifile'."""
        return self.metadata.get("format")

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[TraceEntry]:
        return iter(self._entries)

    def __getitem__(self, index: int) -> TraceEntry:
        return self._entries[index]

    def append(self, entry: TraceEntry) -> None:
        self._entries.append(entry)
        self._invalidate_indexes()

    def extend(self, entries: Iterable[TraceEntry]) -> None:
        self._entries.extend(entries)
        self._invalidate_indexes()

    def replace(self, index: int, entry: TraceEntry) -> None:
        self._entries[index] = entry
        self._invalidate_indexes()

    def clear(self) -> None:
        self._entries.clear()
        self._invalidate_indexes()

    def _invalidate_indexes(self) -> None:
        self._url_index = None
        self._path_index = None
        self._id_index = None

    def _build_url_index(self) -> Dict[str, List[TraceEntry]]:
        if self._url_index is None:
            self._url_index = {}
            for entry in self._entries:
                url_str = str(entry.request.url)
                self._url_index.setdefault(url_str, []).append(entry)
        return self._url_index

    def _build_path_index(self) -> Dict[str, List[TraceEntry]]:
        if self._path_index is None:
            self._path_index = {}
            for entry in self._entries:
                path = entry.request.url.path
                self._path_index.setdefault(path, []).append(entry)
        return self._path_index

    def _build_id_index(self) -> Dict[str, TraceEntry]:
        if self._id_index is None:
            self._id_index = {}
            for entry in self._entries:
                self._id_index.setdefault(entry.id, entry)
        return self._id_index

    # === Getters for various entry queries
    
    def get_entry_by_id(self, entry_id: str) -> Optional[TraceEntry]:
        return self._build_id_index().get(entry_id)

    def get_next_entry_by_id(
        self, entry_id: str, direction: int, n: int = 1
    ) -> Optional[TraceEntry]:
        """
        Gets an entry relative to the entry with the given ID within its manifest stream.

        Args:
            entry_id: The ID of the reference entry
            direction: Direction to move (positive for forward, negative for backward)
            n: Number of steps to move (default: 1)

        Returns:
            The entry at the relative position, or None if not found
        """
        entry = self.get_entry_by_id(entry_id)
        if entry is None:
            return None

        manifest_stream = self.get_manifest_stream(entry.request.url)
        return manifest_stream.get_relative_entry(entry, direction, n)

    def get_entries_for_url(self, url: Union[str, yarl.URL]) -> List[TraceEntry]:
        return self._build_url_index().get(str(url), [])

    def get_entries_by_path(self, path: str) -> List[TraceEntry]:
        return self._build_path_index().get(path, [])

    def get_entries_by_ids(self, entry_ids: Sequence[str]) -> List[TraceEntry]:
        id_index = self._build_id_index()
        missing_ids = [entry_id for entry_id in entry_ids if entry_id not in id_index]
        if missing_ids:
            raise ValueError(f"Entry IDs not found: {', '.join(missing_ids)}")

        selected_ids = set(entry_ids)
        return [entry for entry in self._entries if entry.id in selected_ids]

    def get_entries_by_host(self, host: Optional[str]) -> List[TraceEntry]:
        """
        Retrieves all entries that match the specified host.
        Host matching is case-insensitive.

        Args:
            host: The host string to match. Case-insensitive.
                  Pass None to match entries with no host.

        Returns:
            List of TraceEntry objects matching the host, in order of appearance.
        """
        matching_entries: List[TraceEntry] = []

        if host is None:
            for entry in self._entries:
                try:
                    entry_host = yarl.URL(str(entry.request.url)).host
                    if entry_host is None:
                        matching_entries.append(entry)
                except (AttributeError, TypeError, ValueError):
                    pass
        else:
            host_lower = host.lower()
            for entry in self._entries:
                try:
                    entry_host = yarl.URL(str(entry.request.url)).host
                    if entry_host and entry_host.lower() == host_lower:
                        matching_entries.append(entry)
                except (AttributeError, TypeError, ValueError):
                    pass

        return matching_entries

    def get_entries_for_partial_url(
        self, url_pattern: Union[str, Pattern[str]]
    ) -> List[TraceEntry]:
        matching_entries: List[TraceEntry] = []
        url_index = self._build_url_index()

        if isinstance(url_pattern, re.Pattern):
            for url_str, entries in url_index.items():
                if url_pattern.search(url_str):
                    matching_entries.extend(entries)
        else:
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
        filtered_entries: List[TraceEntry] = []
        for entry in self._entries:
            if host is not None:
                try:
                    entry_host = yarl.URL(str(entry.request.url)).host
                    if entry_host != host:
                        continue
                except (AttributeError, TypeError, ValueError):
                    continue

            if url is not None:
                try:
                    if str(entry.request.url) != url:
                        continue
                except (AttributeError, TypeError):
                    continue

            if partial_url is not None:
                try:
                    if partial_url not in str(entry.request.url):
                        continue
                except (AttributeError, TypeError):
                    continue

            if mime_type is not None:
                try:
                    if entry.response.mime_type != mime_type:
                        continue
                except (AttributeError, TypeError):
                    continue

            filtered_entries.append(entry)
        return filtered_entries

    # === ABR manifest related methods ===

    def get_manifest_stream(self, manifest_url: Union[str, yarl.URL]) -> ManifestStream:
        entries = self.get_entries_for_url(manifest_url)
        if not entries:
            raise ValueError(f"No entries found for manifest URL: {manifest_url}")
        return ManifestStream(entries)

    def get_abr_manifest_urls(
        self, format: Optional[Union[str, Format]] = None
    ) -> List[DecoratedUrl]:
        """
        Get all ABR manifest URLs in the trace.

        Args:
            format: Optional format filter (Format.HLS, Format.DASH, or string like "hls", "dash")

        Returns:
            List of DecoratedUrl objects containing manifest URLs and their formats
        """
        format_filter = format
        if isinstance(format_filter, str):
            format_filter = Format(format_filter)
        urls: List[DecoratedUrl] = []
        ignored_params = self.abr_detector.get_ignored_query_params()

        for entry in self._entries:
            abr_format = Format.from_url_or_mime_type(
                entry.response.mime_type, entry.request.url
            )
            if abr_format is None or (
                format_filter is not None and abr_format != format_filter
            ):
                continue

            # Skip entries with ignored query parameters
            if any(
                entry.request.url.query.get(param) is not None
                for param in ignored_params
            ):
                continue

            urls.append(DecoratedUrl(entry.request.url, abr_format.value))

        return list(set(urls))


class DecoratedUrl:
    """Helper for manifest URL deduplication."""

    def __init__(self, url: yarl.URL, format_value: str):
        self.url = url
        self.format = format_value

    def __hash__(self) -> int:
        return hash((self.url, self.format))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DecoratedUrl):
            return False
        return self.url == other.url and self.format == other.format
