"""
Proxyman writer for exporting TraceEntry objects to Proxyman log v2 format.
"""

import os
import json
import tempfile
import zipfile
from pathlib import Path
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
        output_path_obj = Path(output_path)
        tmp_dir = output_path_obj.parent if output_path_obj.parent != Path(".") else Path(".")
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".proxymanlogv2", dir=str(tmp_dir)
        )
        os.close(tmp_fd)
        tmp_path_obj = Path(tmp_path)

        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
                for entry_data, entry_filename in proxyman_entries:
                    zip_ref.writestr(
                        entry_filename,
                        json.dumps(entry_data, indent=2, ensure_ascii=False),
                    )

            # Move the temporary file to the final location
            tmp_path_obj.replace(output_path_obj)
        except Exception as e:
            # Clean up temporary file on error
            if tmp_path_obj.exists():
                try:
                    tmp_path_obj.unlink()
                except Exception:
                    pass
            raise IOError(
                f"Failed to write Proxyman log file to {output_path}: {e}"
            ) from e

