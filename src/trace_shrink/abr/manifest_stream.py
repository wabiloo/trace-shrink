from __future__ import annotations

import bisect
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from ..entries.trace_entry import TraceEntry
from ..utils.formats import Format


class ManifestStream:
    """
    Represents and manages a single, continuous stream of manifest entries
    from a trace, sorted by time.
    """

    def __init__(self, entries: List[TraceEntry]):
        """
        Initializes the stream with a list of manifest entries.
        The entries are immediately sorted by their request start time to enable
        efficient time-based lookups.

        Args:
            entries: A list of TraceEntry objects for a single manifest URL.

        Raises:
            ValueError: If the list of entries is empty.
        """
        if not entries:
            raise ValueError(
                "Cannot create a ManifestStream with an empty list of entries."
            )

        # Sort entries by the request start timestamp. Handle cases where timestamp might be None.
        def _normalize_timestamp(entry: TraceEntry) -> datetime:
            start = entry.timeline.request_start
            if isinstance(start, datetime):
                return start.astimezone(timezone.utc)
            return datetime.min.replace(tzinfo=timezone.utc)

        self.entries = sorted(entries, key=_normalize_timestamp)
        self.timestamps = [  # Ensure all timestamps are timezone-aware (UTC)
            _normalize_timestamp(entry) for entry in self.entries
        ]
        # Determine format from the first entry
        first_entry = self.entries[0]
        mime_type = first_entry.response.headers.get("content-type", "")
        url = first_entry.request.url
        self.format = Format.from_url_or_mime_type(mime_type, url)

    def get_original_path(self) -> str:
        """Get the original path of the manifest."""
        return self.entries[0].request.url.path

    def find_entry_by_time(
        self,
        target_time: datetime,
        position: Literal["nearest", "before", "after"] = "nearest",
        tolerance: float = 0.0,
    ) -> Optional[TraceEntry]:
        """
        Finds an entry based on a target time, with tolerance and positioning.

        The logic is as follows:
        1. It first searches for entries within the `target_time` +/- `tolerance`.
           If any are found, it returns the one closest to the `target_time`.
        2. If no entries are found within the tolerance, it uses the `position`
           argument to find an entry from the entire stream.

        Args:
            target_time: The datetime to search for.
            position: Determines which entry to select if no match is found
                      within the tolerance. Can be "nearest", "before", or "after".
            tolerance: A float in seconds to create a search window around the
                       target_time.

        Returns:
            A TraceEntry or None if no suitable entry is found.
        """
        if not self.entries:
            return None

        # 1. Primary search within the tolerance window
        if tolerance > 0:
            start_window = target_time - timedelta(seconds=tolerance)
            end_window = target_time + timedelta(seconds=tolerance)

            start_index = bisect.bisect_left(self.timestamps, start_window)
            end_index = bisect.bisect_right(self.timestamps, end_window)

            candidate_entries = self.entries[start_index:end_index]

            if candidate_entries:
                # If matches are found, return the one truly closest to target_time
                return min(
                    candidate_entries,
                    key=lambda e: abs(e.timeline.request_start - target_time),
                )

        # 2. If no match in tolerance window, apply the `position` logic
        if position == "nearest":
            insertion_point = bisect.bisect_left(self.timestamps, target_time)
            if insertion_point == 0:
                return self.entries[0]
            if insertion_point == len(self.timestamps):
                return self.entries[-1]

            before_entry = self.entries[insertion_point - 1]
            after_entry = self.entries[insertion_point]

            if (target_time - before_entry.timeline.request_start) < (
                after_entry.timeline.request_start - target_time
            ):
                return before_entry
            else:
                return after_entry

        elif position == "after":
            insertion_point = bisect.bisect_right(self.timestamps, target_time)
            if insertion_point < len(self.timestamps):
                return self.entries[insertion_point]
            return None  # No entry is after the target_time

        elif position == "before":
            insertion_point = bisect.bisect_left(self.timestamps, target_time)
            if insertion_point > 0:
                return self.entries[insertion_point - 1]
            return None  # No entry is before the target_time

        return None

    def get_relative_entry(
        self, entry: TraceEntry, direction: int, n: int = 1
    ) -> Optional[TraceEntry]:
        """
        Gets the nth entry relative to the given entry in this manifest stream.

        Args:
            entry: The reference entry to navigate from.
            direction: 1 for forward (next), -1 for backward (previous).
            n: Number of entries to skip (default: 1).

        Returns:
            The TraceEntry at the calculated position, or None if:
            - The entry is not found in this stream
            - The calculated position is out of bounds

        Examples:
            get_relative_entry(entry, 1, 1)  # Next entry
            get_relative_entry(entry, -1, 1)  # Previous entry
            get_relative_entry(entry, 1, 3)  # 3rd next entry
        """
        try:
            current_index = self.entries.index(entry)
        except ValueError:
            return None

        new_index = current_index + (direction * n)

        if 0 <= new_index < len(self.entries):
            return self.entries[new_index]
        return None

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, index: int) -> TraceEntry:
        return self.entries[index]
