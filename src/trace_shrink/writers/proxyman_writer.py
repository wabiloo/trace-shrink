"""
Proxyman writer for exporting TraceEntry objects to Proxyman log v2 format.
"""

import json
import os
import tempfile
import zipfile
from typing import List

from ..entries.proxyman_entry import ProxymanLogV2Entry
from ..entries.trace_entry import TraceEntry


class ProxymanWriter:
    """Writer for Proxyman log v2 format files."""

    @staticmethod
    def write(entries: List[TraceEntry], output_path: str) -> None:
        """
        Write a list of TraceEntry objects to a Proxyman log v2 file.

        Args:
            entries: List of TraceEntry objects to export.
            output_path: Path where the Proxyman log file will be written.

        Raises:
            IOError: If the file cannot be written.
        """
        proxyman_entries = [
            ProxymanLogV2Entry.from_trace_entry(entry, index)
            for index, entry in enumerate(entries)
        ]

        # Create a temporary file for the ZIP archive
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".proxymanlogv2", dir=os.path.dirname(output_path) or "."
        )
        os.close(tmp_fd)

        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
                for entry_data, entry_filename in proxyman_entries:
                    zip_ref.writestr(
                        entry_filename,
                        json.dumps(entry_data, indent=2, ensure_ascii=False),
                    )

            # Move the temporary file to the final location
            os.replace(tmp_path, output_path)
        except Exception as e:
            # Clean up temporary file on error
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise IOError(
                f"Failed to write Proxyman log file to {output_path}: {e}"
            ) from e

