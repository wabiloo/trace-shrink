# src/abr_capture_spy/har_reader.py
import json
from typing import Any, Dict, Optional

from ..entries.har_entry import HarEntry
from ..trace import Trace
from .trace_reader import TraceReader


class HarReader(TraceReader):
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
        self._raw_har_data: Optional[Dict[str, Any]] = None
        self._entries_loaded = False

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

            # --- Structure looks OK, store raw data but don't create entries yet ---
            self._raw_har_data = loaded_data
            # Entries will be created lazily when trace is accessed

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
    def trace(self) -> Trace:
        """Lazy-load entries when trace is accessed."""
        if not self._entries_loaded:
            self._populate_trace_entries()
        return self._trace

    def _populate_trace_entries(self) -> None:
        """Create HarEntry objects from raw HAR data."""
        if self._entries_loaded or not self._raw_har_data:
            return

        har_log = self._raw_har_data.get("log", {})
        raw_entries = har_log.get("entries", [])
        for i, raw_entry_data in enumerate(raw_entries):
            if isinstance(raw_entry_data, dict):
                entry = HarEntry(raw_entry_data, self, i)
                self._trace.append(entry)

        self._entries_loaded = True

    # Placeholder for other potential methods specific to HarReader or common to TraceReader
    # For example, getting creator info, browser info from HAR log.
    def get_har_log_version(self) -> Optional[str]:
        return self._raw_har_data.get("log", {}).get("version")

    def get_har_creator_info(self) -> Optional[Dict[str, Any]]:
        return self._raw_har_data.get("log", {}).get("creator")
