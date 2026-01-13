"""
HAR writer for exporting TraceEntry objects to HAR format.
"""

import json
from typing import Any, Dict, List

from ..entries.har_entry import HarEntry
from ..entries.trace_entry import TraceEntry
from ..version import get_package_version


class HarWriter:
    """Writer for HAR (HTTP Archive) format files."""

    @staticmethod
    def write(entries: List[TraceEntry], output_path: str) -> None:
        """
        Write a list of TraceEntry objects to a HAR file.

        Args:
            entries: List of TraceEntry objects to export.
            output_path: Path where the HAR file will be written.

        Raises:
            IOError: If the file cannot be written.
        """
        har_data = HarWriter._build_har_structure(entries)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(har_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            raise IOError(f"Failed to write HAR file to {output_path}: {e}") from e

    @staticmethod
    def _build_har_structure(entries: List[TraceEntry]) -> Dict[str, Any]:
        """
        Build the complete HAR file structure from entries.

        Args:
            entries: List of TraceEntry objects to convert.

        Returns:
            Dictionary representing the HAR file structure.
        """
        har_entries = [
            HarEntry.from_trace_entry(entry, index)
            for index, entry in enumerate(entries)
        ]

        return {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "trace-shrink",
                    "version": get_package_version(),
                },
                "entries": har_entries,
            }
        }

