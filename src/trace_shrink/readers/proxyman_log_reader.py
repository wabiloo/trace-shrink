import functools
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..entries.proxyman_entry import ProxymanLogV2Entry
from ..trace import Trace
from .trace_reader import TraceReader


class ProxymanLogV2Reader(TraceReader):
    """
    Handles reading and indexing Proxyman log files (.proxymanlogv2).
    Ensures lazy loading of entry details.
    """

    REQUEST_FILE_PATTERN = re.compile(r"request_(\d+)_([a-zA-Z0-9_-]+)")

    def __init__(self, log_file_path: str):
        """
        Initializes the reader with the path to the .proxymanlogv2 file.

        Args:
            log_file_path: The path to the .proxymanlogv2 file.

        Raises:
            FileNotFoundError: If the log file does not exist.
            ValueError: If the file is not a valid zip archive.
            RuntimeError: For other unexpected errors during initialization.
        """
        super().__init__()
        self.log_file_path = log_file_path
        log_path = Path(self.log_file_path)
        if not log_path.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_file_path}")
        if not zipfile.is_zipfile(self.log_file_path):
            raise ValueError(
                f"File is not a valid Proxyman log (zip archive): {self.log_file_path}"
            )

        self._index: Dict[str, Dict[str, Any]] = {}
        self._parsed_entries_cache: Dict[str, ProxymanLogV2Entry] = {}
        self._trace_populated = False
        try:
            self._scan_and_index()
            # Don't populate entries eagerly - lazy load when trace is accessed
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize ProxymanLogV2Reader due to scan error: {e}"
            )

    def _scan_and_index(self) -> None:
        """
        Scans the zip archive and builds an index of request entries.
        This index contains only essential metadata to keep loading fast.
        Full entry data is loaded lazily by get_entry().
        """
        indexed_count = 0
        skipped_malformed_json = 0
        skipped_other_content_error = 0
        processed_matching_filenames = 0

        try:
            with zipfile.ZipFile(self.log_file_path, "r") as zip_ref:
                all_files_in_zip = zip_ref.namelist()
                for filename_in_zip in all_files_in_zip:
                    match = self.REQUEST_FILE_PATTERN.fullmatch(filename_in_zip)
                    if match:
                        processed_matching_filenames += 1
                        index_str, entry_id_from_filename = match.groups()

                        current_index_entry_metadata = {
                            "id": entry_id_from_filename,
                            "index": int(index_str),
                            "host": None,
                            "uri": None,
                        }

                        try:
                            with zip_ref.open(filename_in_zip) as entry_content_file:
                                content_json = json.load(entry_content_file)
                                request_data_json = content_json.get("request", {})
                                current_index_entry_metadata["host"] = (
                                    request_data_json.get("host")
                                )
                                current_index_entry_metadata["uri"] = (
                                    request_data_json.get("uri")
                                )
                        except json.JSONDecodeError:
                            skipped_malformed_json += 1
                        except Exception:
                            skipped_other_content_error += 1

                        self._index[filename_in_zip] = current_index_entry_metadata
                        indexed_count += 1
        except zipfile.BadZipFile as e:
            raise ValueError(
                f"Corrupted or invalid zip archive: {self.log_file_path} - {e}"
            )
        except Exception as e:
            raise RuntimeError(f"Unexpected error during archive scan: {e}")

    @property
    def trace(self) -> Trace:
        """Lazy-load entries when trace is accessed."""
        if not self._trace_populated:
            self._populate_trace_entries()
        return self._trace

    def _populate_trace_entries(self) -> None:
        if self._trace_populated:
            return

        for filename in self._sorted_index:
            entry = self._parse_entry(filename)
            if entry:
                self._trace.append(entry)

        self._trace_populated = True

    @functools.cached_property
    def _sorted_index(self) -> List[str]:
        """Returns a list of all indexed request entry filenames, sorted by their numerical index.
        It reflects the actual time-based order of the requests in the archive.
        This is a cached property."""
        sorted_items = sorted(self._index.items(), key=lambda item: item[1]["index"])
        return [filename for filename, _ in sorted_items]

    def get_index(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns the generated lightweight index.

        The index maps the internal filename (e.g., 'request_1_86') to a
        dictionary containing extracted metadata like 'id', 'index', 'host', and 'uri'.
        Host and URI might be None if the entry content was unreadable during indexing.
        """
        return self._index.copy()

    def _parse_entry(self, entry_filename: str) -> Optional[ProxymanLogV2Entry]:
        """
        Retrieves a specific entry by its internal filename and returns it as a ProxymanLogV2Entry object.
        This method loads the full JSON content for the specified entry.
        Entries are cached to preserve modifications.

        Args:
            entry_filename: The internal filename of the entry (e.g., 'request_1_86').

        Returns:
            A ProxymanLogV2Entry object, or None if not found or if parsing fails.
        """
        if entry_filename not in self._index:
            return None

        # Return cached entry if available (preserves modifications)
        if entry_filename in self._parsed_entries_cache:
            return self._parsed_entries_cache[entry_filename]

        try:
            with zipfile.ZipFile(self.log_file_path, "r") as zip_ref:
                if entry_filename not in zip_ref.namelist():
                    return None
                with zip_ref.open(entry_filename) as entry_file_content:
                    json_content = json.load(entry_file_content)
                    entry = ProxymanLogV2Entry(entry_filename, json_content, self)
                    # Cache the entry to preserve modifications
                    self._parsed_entries_cache[entry_filename] = entry
                    return entry
        except json.JSONDecodeError:
            return None
        except zipfile.BadZipFile:
            return None
        except KeyError:
            return None
        except Exception:
            return None
