import functools
import json
import os
import re
import shutil
import tempfile
import zipfile
from typing import Any, Dict, Iterator, List, Optional

from .archive_reader import ArchiveReader
from .proxyman_entry import ProxymanLogV2Entry
from .trace_entry import TraceEntry


class ProxymanLogV2Reader(ArchiveReader):
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
        if not os.path.exists(self.log_file_path):
            raise FileNotFoundError(f"Log file not found: {self.log_file_path}")
        if not zipfile.is_zipfile(self.log_file_path):
            raise ValueError(
                f"File is not a valid Proxyman log (zip archive): {self.log_file_path}"
            )

        self._index: Dict[str, Dict[str, Any]] = {}
        self._parsed_entries_cache: Dict[str, ProxymanLogV2Entry] = {}
        try:
            self._scan_and_index()
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

    def __len__(self) -> int:
        """Returns the total number of indexed entries."""
        return len(self._index)

    def __iter__(self) -> Iterator[ProxymanLogV2Entry]:
        """Iterates over all ProxymanLogV2Entry objects in the archive, sorted by their numerical index."""
        all_entry_filenames = self._sorted_index
        for filename in all_entry_filenames:
            entry_obj = self._parse_entry(filename)
            if entry_obj:
                yield entry_obj

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

    @property
    def entries(self) -> List[ProxymanLogV2Entry]:
        """
        Returns a list of all ProxymanLogV2Entry objects, sorted by their numerical index.

        Accessing this property will trigger the loading of all entries from the archive.
        For lazy iteration, directly iterate over the reader instance (e.g., `for entry in reader:`).
        """
        return list(self)

    @functools.lru_cache(maxsize=256)
    def list_entries_by_host(self, host_to_match: Optional[str]) -> List[str]:
        """
        Returns a list of indexed request entry filenames that match the specified host,
        sorted by their numerical index. Matching is case-insensitive.
        If host_to_match is None, returns entries where the host in index is None.
        """
        if host_to_match is None:
            filtered_items = [
                item for item in self._index.items() if item[1].get("host") is None
            ]
        else:
            host_to_match_lower = host_to_match.lower()
            filtered_items = [
                item
                for item in self._index.items()
                if item[1].get("host")
                and item[1]["host"].lower() == host_to_match_lower
            ]

        sorted_items = sorted(filtered_items, key=lambda item: item[1]["index"])
        return [filename for filename, _ in sorted_items]

    def get_entries_by_host(
        self, host_to_match: Optional[str]
    ) -> Iterator[ProxymanLogV2Entry]:
        """
        Retrieves all entries that match the specified host, yielding them one by one,
        sorted by their numerical index. Host matching is case-insensitive.
        If host_to_match is None, yields entries where host is None.

        Args:
            host_to_match: The host string to match. Case-insensitive.
                           Pass None to match entries with no host.

        Yields:
            ProxymanLogV2Entry: The next matching entry object, sorted by index.
        """
        entry_filenames = self.list_entries_by_host(host_to_match)

        for filename in entry_filenames:
            entry_obj = self._parse_entry(entry_filename=filename)
            if entry_obj:
                yield entry_obj

    # def get_entries_for_url(self, url_pattern: str) -> List[CaptureEntry]:
    #     """
    #     Retrieves entries whose request URL matches the given regex pattern.
    #     This implementation iterates through all entries, which can be slow for large archives.
    #     Consider optimizing if this is a frequent operation.

    #     Args:
    #         url_pattern: A regex pattern to match against the request URI.

    #     Returns:
    #         A list of ProxymanLogV2Entry objects whose request URI matches the pattern.
    #     """
    #     matching_entries: List[CaptureEntry] = []
    #     url_regex = re.compile(url_pattern)

    #     for entry_obj in self:
    #         if entry_obj:
    #             try:
    #                 current_url_str = str(entry_obj.request.url)
    #                 if url_regex.search(current_url_str):
    #                     matching_entries.append(entry_obj)
    #             except Exception:
    #                 pass

    #     return matching_entries

    def save(self, output_path: Optional[str] = None) -> None:
        """
        Save the modified Proxyman log file to disk.

        This method creates a new ZIP archive with updated entries.
        Since ZIP files don't support in-place updates efficiently, we create
        a new archive with all original files plus any modified entries.

        Args:
            output_path: Optional path to save the file. If not provided,
                        saves to the original file path.

        Raises:
            IOError: If the file cannot be written.
            RuntimeError: If there's an error processing the archive.
        """
        path = output_path or self.log_file_path

        # Create a temporary file for the new archive
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".proxymanlogv2", dir=os.path.dirname(path) or "."
        )
        os.close(tmp_fd)

        try:
            # Track which entries have been parsed/modified (use cache if available)
            modified_entries: Dict[str, Dict[str, Any]] = {}
            # Use cached entries if available, otherwise parse them
            for entry_filename in self._sorted_index:
                if entry_filename in self._parsed_entries_cache:
                    # Use cached entry (preserves modifications)
                    entry = self._parsed_entries_cache[entry_filename]
                    modified_entries[entry_filename] = entry._raw_data
                else:
                    # Parse entry if not cached
                    entry = self._parse_entry(entry_filename)
                    if entry:
                        modified_entries[entry_filename] = entry._raw_data

            # Create a new ZIP archive with updated entries
            with zipfile.ZipFile(self.log_file_path, "r") as source_zip:
                with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dest_zip:
                    # Copy all files from the original archive
                    for item in source_zip.infolist():
                        # If this is a modified entry, write the updated version
                        if item.filename in modified_entries:
                            entry_data = modified_entries[item.filename]
                            dest_zip.writestr(
                                item.filename,
                                json.dumps(entry_data, indent=2, ensure_ascii=False),
                            )
                        else:
                            # Copy the original file as-is
                            dest_zip.writestr(item, source_zip.read(item.filename))

            # Replace the original file with the updated one
            shutil.move(tmp_path, path)

        except Exception as e:
            # Clean up temporary file on error
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise RuntimeError(
                f"Failed to save Proxyman log file to {path}: {e}"
            ) from e

    @staticmethod
    def export_entries(entries: List[TraceEntry], output_path: str) -> None:
        """
        Export a list of TraceEntry objects to a Proxyman log v2 file.

        Args:
            entries: List of TraceEntry objects to export.
            output_path: Path where the Proxyman log file will be written.

        Raises:
            IOError: If the file cannot be written.
        """
        from .proxyman_entry import ProxymanLogV2Entry

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
