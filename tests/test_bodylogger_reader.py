import pytest
from datetime import datetime
from pathlib import Path

from trace_shrink import BodyLoggerReader, BodyLoggerEntry, open_archive
from trace_shrink.archive_reader import ArchiveReader


# Path to test bodylogger file
TEST_BODYLOGGER_PATH = Path(__file__).parent / "archives" / "bodylogger.log"


class TestBodyLoggerReader:
    """Tests for BodyLoggerReader class."""

    def test_init_with_valid_file(self):
        """Test initialization with a valid bodylogger file."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        assert isinstance(reader, BodyLoggerReader)
        assert isinstance(reader, ArchiveReader)
        assert len(reader.entries) > 0

    def test_init_with_nonexistent_file(self):
        """Test initialization with a non-existent file."""
        with pytest.raises(FileNotFoundError):
            BodyLoggerReader("nonexistent_file.log")

    def test_entries_property(self):
        """Test that entries property returns a list of BodyLoggerEntry objects."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entries = reader.entries
        assert isinstance(entries, list)
        assert all(isinstance(entry, BodyLoggerEntry) for entry in entries)

    def test_len(self):
        """Test that __len__ returns the correct number of entries."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        assert len(reader) == len(reader.entries)
        assert len(reader) > 0

    def test_iter(self):
        """Test that __iter__ allows iteration over entries."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entries_list = list(reader)
        assert len(entries_list) == len(reader)
        assert all(isinstance(entry, BodyLoggerEntry) for entry in entries_list)

    def test_entry_basic_properties(self):
        """Test basic properties of a BodyLoggerEntry."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Test index
        assert entry.index == 0

        # Test id
        assert isinstance(entry.id, str)

        # Test comment (should be log_type)
        assert entry.comment in ["ORIGIN", "MANIPULATED_MANIFEST"]

        # Test highlight (should be None)
        assert entry.highlight is None

    def test_entry_request_details(self):
        """Test request details of a BodyLoggerEntry."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Test request URL
        assert entry.request.url is not None
        assert "mm" in str(entry.request.url).lower()

        # Test request method
        assert entry.request.method == "GET"

        # Test request headers
        headers = entry.request.headers
        assert isinstance(headers, dict)
        assert "correlation-id" in headers

    def test_entry_response_details(self):
        """Test response details of a BodyLoggerEntry."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        # Find an entry with DASH manifest
        dash_entry = None
        for entry in reader.entries:
            if entry.response.mime_type == "application/dash+xml":
                dash_entry = entry
                break

        assert dash_entry is not None, "Should find at least one DASH manifest"

        # Test response status code
        assert dash_entry.response.status_code == 200

        # Test response mime_type
        assert dash_entry.response.mime_type == "application/dash+xml"

        # Test response headers
        headers = dash_entry.response.headers
        assert isinstance(headers, dict)
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/dash+xml"

    def test_entry_response_body(self):
        """Test response body details of a BodyLoggerEntry."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Test body text
        body_text = entry.response.body.text
        assert body_text is not None
        assert len(body_text) > 0

        # Test body size
        raw_size = entry.response.body.raw_size
        assert raw_size is not None
        assert raw_size > 0

        # Test that DASH content starts correctly
        if entry.response.mime_type == "application/dash+xml":
            assert "<?xml" in body_text or "<MPD" in body_text

    def test_entry_timeline_details(self):
        """Test timeline details of a BodyLoggerEntry."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Test request_start
        assert entry.timeline.request_start is not None
        assert isinstance(entry.timeline.request_start, datetime)

        # Test response_end
        assert entry.timeline.response_end is not None
        assert isinstance(entry.timeline.response_end, datetime)

        # Test that response_end is after request_start
        assert entry.timeline.response_end >= entry.timeline.request_start

    def test_entry_bodylogger_specific_properties(self):
        """Test bodylogger-specific properties."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Test service_id
        assert entry.service_id is not None
        assert isinstance(entry.service_id, str)

        # Test session_id (may be None)
        # session_id is optional, so we just check it's either str or None
        assert entry.session_id is None or isinstance(entry.session_id, str)

        # Test correlation_id
        assert isinstance(entry.correlation_id, int)

    def test_query_by_log_type(self):
        """Test filtering entries by log type."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        origin_entries = reader.query(log_type="ORIGIN")
        assert all(entry.comment == "ORIGIN" for entry in origin_entries)

        manipulated_entries = reader.query(log_type="MANIPULATED_MANIFEST")
        assert all(
            entry.comment == "MANIPULATED_MANIFEST" for entry in manipulated_entries
        )

    def test_query_by_service_id(self):
        """Test filtering entries by service ID."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        # Get service_id from first entry
        service_id = reader.entries[0].service_id
        filtered_entries = reader.query(service_id=service_id)

        assert all(entry.service_id == service_id for entry in filtered_entries)
        assert len(filtered_entries) > 0

    def test_query_by_session_id(self):
        """Test filtering entries by session ID."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        # Get session_id from first entry that has one
        session_id = None
        for entry in reader.entries:
            if entry.session_id:
                session_id = entry.session_id
                break

        if session_id:
            filtered_entries = reader.query(session_id=session_id)
            assert all(entry.session_id == session_id for entry in filtered_entries)
            assert len(filtered_entries) > 0

    def test_query_by_time_range(self):
        """Test filtering entries by time range."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        if len(reader.entries) < 2:
            pytest.skip("Need at least 2 entries for time range test")

        first_time = reader.entries[0].timeline.request_start
        last_time = reader.entries[-1].timeline.request_start

        # Query for entries in the full range
        filtered_entries = reader.query(start_time=first_time, end_time=last_time)
        assert len(filtered_entries) == len(reader.entries)

        # Query for entries after a certain time
        mid_time = reader.entries[len(reader.entries) // 2].timeline.request_start
        filtered_entries = reader.query(start_time=mid_time)
        assert len(filtered_entries) <= len(reader.entries)

    def test_open_archive_with_bodylogger(self):
        """Test that open_archive can handle bodylogger files."""
        reader = open_archive(str(TEST_BODYLOGGER_PATH))
        assert isinstance(reader, BodyLoggerReader)
        assert isinstance(reader, ArchiveReader)
        assert len(reader) > 0

    def test_content_type_detection(self):
        """Test that content types are correctly detected."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        # Check for DASH content
        dash_entries = [
            e for e in reader if e.response.mime_type == "application/dash+xml"
        ]
        assert len(dash_entries) > 0

        # Verify DASH content actually contains MPD
        for entry in dash_entries:
            content = entry.response.body.text
            assert "<MPD" in content or "mpd" in content.lower()

    def test_url_construction(self):
        """Test that URLs are correctly constructed."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        url = entry.request.url
        url_str = str(url)

        # URL should contain the host and log type
        assert "mm" in url_str.lower()
        assert (
            "-origin" in url_str.lower() or "-manipulated_manifest" in url_str.lower()
        )

    def test_query_params_in_url(self):
        """Test that query parameters are included in URLs."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))

        # Find an entry with query params
        entry_with_params = None
        for entry in reader.entries:
            if entry.request.url.query:
                entry_with_params = entry
                break

        if entry_with_params:
            query = entry_with_params.request.url.query
            assert len(query) > 0


class TestBodyLoggerEntry:
    """Tests specific to BodyLoggerEntry class."""

    def test_get_raw_data(self):
        """Test that get_raw_data returns the underlying dictionary."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        raw_data = entry.get_raw_data()
        assert isinstance(raw_data, dict)
        assert "timestamp" in raw_data
        assert "request_line" in raw_data
        assert "body" in raw_data

    def test_content_property(self):
        """Test the content property that returns body text."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        content = entry.content
        # Content should be text for DASH/XML
        if entry.response.mime_type in ["application/dash+xml", "application/xml"]:
            assert isinstance(content, str)
            assert len(content) > 0

    def test_set_comment(self):
        """Test setting a comment on an entry (in-memory only)."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Get original comment (log_type)
        original_comment = entry.comment
        assert original_comment is not None

        # Set a new comment
        new_comment = "Test comment"
        entry.set_comment(new_comment)

        # Verify comment changed
        assert entry.comment == new_comment
        assert entry.comment != original_comment

    def test_set_highlight(self):
        """Test setting a highlight on an entry (in-memory only)."""
        reader = BodyLoggerReader(str(TEST_BODYLOGGER_PATH))
        entry = reader.entries[0]

        # Initially should be None
        assert entry.highlight is None

        # Set a highlight
        entry.set_highlight("red")

        # Verify highlight changed
        assert entry.highlight == "red"

        # Change to another highlight
        entry.set_highlight("yellow")
        assert entry.highlight == "yellow"
