import re
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from .archive_reader import ArchiveReader
from .bodylogger_entry import BodyLoggerEntry


def _get_content_type(body: str) -> str:
    """Determines the Content-Type based on the response body content."""
    body_lines = body.strip().split("\n")

    # Check first 3 lines for <MPD
    for line in body_lines[:3]:
        if "<MPD" in line:
            return "application/dash+xml"

    if "#EXTM3U" in body:
        return "application/x-mpegURL"

    # Use regex for more flexible matching of VAST and VMAP
    if re.search(r"<(\w*:)?VAST", body, re.IGNORECASE):
        return "application/vnd.vast+xml"

    if re.search(r"<(\w*:)?VMAP", body, re.IGNORECASE):
        return "application/vnd.vmap+xml"

    if body_lines and body_lines[0].strip().startswith("<?xml"):
        return "application/xml"

    return "text/plain"


class BodyLoggerReader(ArchiveReader):
    """
    Handles reading and indexing bodylogger log files.
    """

    def __init__(self, log_file_path: str):
        """
        Initializes the reader with the path to the bodylogger file.

        Args:
            log_file_path: The path to the bodylogger file.

        Raises:
            FileNotFoundError: If the bodylogger file does not exist.
            RuntimeError: For other unexpected errors during initialization.
        """
        super().__init__()
        self.log_file_path = log_file_path
        self._entries: List[BodyLoggerEntry] = []
        self._records: List[Dict[str, Any]] = []

        try:
            self._parse_file()
        except FileNotFoundError:
            raise FileNotFoundError(f"Bodylogger file not found: {self.log_file_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize BodyLoggerReader: {e}") from e

    def _parse_file(self) -> None:
        """
        Parses the bodylogger file and creates BodyLoggerEntry objects.
        """
        with open(self.log_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by timestamp pattern
        log_entries = re.split(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,:]\d{3})", content
        )

        for i in range(1, len(log_entries), 2):
            timestamp_str = log_entries[i]
            entry_content = log_entries[i + 1]

            lines = entry_content.strip().split("\n")

            try:
                # --- Timestamp ---
                if timestamp_str[19] == ":":
                    timestamp_str = f"{timestamp_str[:19]},{timestamp_str[20:]}"
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")

                # --- Initialize fields ---
                request_line = ""
                correlation_id = 0
                request_time = 0.0
                query_params = ""
                headers = {}
                body_content = []
                log_type, service_id, session_id = None, None, None

                # --- State-machine-like parsing ---
                in_headers = False
                in_body = False
                in_query_params = False
                query_params_accum: List[str] = []

                # Extract request_time from first line
                time_match = re.search(r"request_time=([\d.]+)", lines[0])
                if time_match:
                    request_time = float(time_match.group(1))

                for line in lines:
                    stripped_line = line.strip()

                    if "REQUEST:" in line:
                        full_request_line = line.split("REQUEST:")[1].strip()
                        try:
                            path, req_id = full_request_line.rsplit("_", 1)
                            correlation_id = int(req_id)
                            request_line = path
                        except (ValueError, IndexError):
                            request_line = full_request_line
                            correlation_id = 0
                        continue

                    if "-- Query params:" in line:
                        in_query_params = True
                        query_params_accum = []
                        continue

                    # Handle query params section
                    if in_query_params:
                        if stripped_line.startswith("-- ") or (
                            stripped_line.startswith("[") and "_START" in stripped_line
                        ):
                            query_params = "&".join(query_params_accum)
                            in_query_params = False
                            # Fall through to process this line
                        else:
                            if "=" in stripped_line:
                                query_params_accum.append(stripped_line)
                            continue

                    if stripped_line == "-- Headers:":
                        in_headers = True
                        continue

                    if stripped_line.startswith("[") and "_START" in stripped_line:
                        in_headers = False
                        in_body = True
                        start_tag_match = re.match(
                            r"\[(\w+)_START ([\w-]+)(?: ([\w.-]+))?\]", stripped_line
                        )
                        if start_tag_match:
                            log_type = start_tag_match.group(1)
                            service_id = start_tag_match.group(2)
                            session_id = start_tag_match.group(3)
                        continue

                    if stripped_line.startswith("[") and "_END" in stripped_line:
                        in_body = False
                        break

                    if in_headers:
                        if ": " in line:
                            key, value = line.split(": ", 1)
                            headers[key.strip()] = value.strip()

                    if in_body:
                        body_content.append(line)

                # Finalize query params if section reached EOF without a new marker
                if in_query_params and not query_params:
                    query_params = "&".join(query_params_accum)

                # --- Record Creation ---
                if log_type and service_id:
                    body = "\n".join(body_content)
                    content_type = _get_content_type(body)

                    record = {
                        "timestamp": timestamp,
                        "request_line": request_line,
                        "correlation_id": correlation_id,
                        "request_time": request_time,
                        "query_params": query_params,
                        "headers": headers,
                        "body": body,
                        "log_type": log_type,
                        "service_id": service_id,
                        "session_id": session_id,
                        "content_type": content_type,
                    }
                    self._records.append(record)

            except (IndexError, ValueError):
                # Skip malformed log entries
                pass

        # Create BodyLoggerEntry objects from parsed records
        for idx, record in enumerate(self._records):
            entry = BodyLoggerEntry(record, self, idx)
            self._entries.append(entry)

    @property
    def entries(self) -> List[BodyLoggerEntry]:
        """Returns a list of all BodyLoggerEntry objects."""
        return self._entries

    def __len__(self) -> int:
        """Returns the total number of entries."""
        return len(self._entries)

    def __iter__(self) -> Iterator[BodyLoggerEntry]:
        """Iterates over all entries in the archive."""
        return iter(self._entries)

    def query(
        self,
        log_type: Optional[str] = None,
        service_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[BodyLoggerEntry]:
        """
        Filters log entries based on the provided criteria.

        Args:
            log_type: Filter by log type (e.g., "REQUEST", "RESPONSE").
            service_id: Filter by service ID.
            session_id: Filter by session ID.
            start_time: Filter by entries after or at this time.
            end_time: Filter by entries before or at this time.

        Returns:
            A list of BodyLoggerEntry objects matching the criteria.
        """
        filtered_entries = self._entries

        if log_type:
            filtered_entries = [
                e
                for e in filtered_entries
                if e.comment and e.comment.lower() == log_type.lower()
            ]

        if service_id:
            filtered_entries = [
                e for e in filtered_entries if e.service_id == service_id
            ]

        if session_id:
            filtered_entries = [
                e for e in filtered_entries if e.session_id == session_id
            ]

        if start_time:
            filtered_entries = [
                e
                for e in filtered_entries
                if e.timeline.request_start and e.timeline.request_start >= start_time
            ]

        if end_time:
            filtered_entries = [
                e
                for e in filtered_entries
                if e.timeline.request_start and e.timeline.request_start <= end_time
            ]

        return filtered_entries
