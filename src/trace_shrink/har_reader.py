# src/abr_capture_spy/har_reader.py
import json
from typing import Any, Dict, Iterator, List, Optional

from .archive_reader import ArchiveReader
from .har_entry import HarEntry
from .trace_entry import TraceEntry  # For type hinting


class HarReader(ArchiveReader):
    """
    Handles reading and indexing HAR (HTTP Archive) files (.har).
    """

    def __init__(self, har_file_path: str):
        """
        Initializes the reader with the path to the .har file.

        Args:
            har_file_path: The path to the .har file.

        Raises:
            FileNotFoundError: If the HAR file does not exist.
            ValueError: If the file content is not valid JSON or not a HAR structure.
        """
        super().__init__()
        self.har_file_path = har_file_path
        self._entries: List[HarEntry] = []
        self._raw_har_data: Optional[Dict[str, Any]] = None

        try:
            with open(self.har_file_path, "r", encoding="utf-8-sig") as f:
                loaded_data = json.load(f)

            # --- Explicit check if loaded data is a dictionary ---
            # If json.load didn't raise an error but returned non-dict, treat as invalid JSON for HAR context
            if not isinstance(loaded_data, dict):
                raise ValueError(
                    f"Invalid JSON structure: Root is not an object in {self.har_file_path}."
                )

            # --- Now perform HAR structural validation ---
            if "log" not in loaded_data:
                raise ValueError("Invalid HAR format: 'log' object not found.")
            har_log = loaded_data.get("log")
            if not isinstance(har_log, dict) or "entries" not in har_log:
                raise ValueError(
                    "Invalid HAR format: 'log.entries' not found or 'log' is not an object."
                )
            raw_entries = har_log.get("entries", [])
            if not isinstance(raw_entries, list):
                raise ValueError("Invalid HAR format: 'log.entries' is not a list.")

            # --- Structure looks OK, store and process entries ---
            self._raw_har_data = loaded_data
            for i, raw_entry_data in enumerate(raw_entries):
                if isinstance(raw_entry_data, dict):
                    entry = HarEntry(raw_entry_data, self, i)
                    self._entries.append(entry)

        except FileNotFoundError:
            # Keep specific error for file not found
            raise FileNotFoundError(f"HAR file not found: {self.har_file_path}")
        except json.JSONDecodeError as e:
            # This is the expected path for truly malformed JSON
            raise ValueError(f"Invalid JSON in HAR file: {self.har_file_path} - {e}")
        except ValueError as e:
            # Re-raise ValueErrors from structure checks, adding context
            # Use repr(e) to include the original error message
            raise ValueError(f"Invalid HAR structure in {self.har_file_path}: {e!r}")
        except Exception as e:
            # Catch-all for other unexpected errors
            raise RuntimeError(
                f"Could not read or process HAR file {self.har_file_path}: {e!r}"
            )

    @property
    def entries(self) -> List[HarEntry]:
        """Returns a list of all HarEntry objects."""
        return self._entries

    # --- Implementation of ArchiveReader abstract methods ---

    # def get_entries_for_url(self, url_pattern: str) -> List[CaptureEntry]:
    #     """
    #     Retrieves entries whose request URL matches the given regex pattern.

    #     Args:
    #         url_pattern: A regex pattern to match against the request URL.

    #     Returns:
    #         A list of HarEntry objects whose request URL matches the pattern.
    #     """
    #     matching_entries: List[CaptureEntry] = []
    #     url_regex = re.compile(url_pattern)

    #     for entry in self._entries:
    #         try:
    #             current_url_str = str(entry.request.url)
    #             if url_regex.search(current_url_str):
    #                 matching_entries.append(entry)
    #         except Exception:
    #             # Handle cases where URL might be malformed or access fails
    #             pass
    #     return matching_entries

    def __len__(self) -> int:
        """Returns the total number of entries."""
        return len(self._entries)

    def __iter__(self) -> Iterator[HarEntry]:  # Type hint concrete type
        """Iterates over all entries in the archive."""
        return iter(self._entries)

    # Placeholder for other potential methods specific to HarReader or common to ArchiveReader
    # For example, getting creator info, browser info from HAR log.
    def get_har_log_version(self) -> Optional[str]:
        return self._raw_har_data.get("log", {}).get("version")

    def get_har_creator_info(self) -> Optional[Dict[str, Any]]:
        return self._raw_har_data.get("log", {}).get("creator")
