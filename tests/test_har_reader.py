# tests/test_har_reader.py
import json
from pathlib import Path
from typing import Any

import pytest
from yarl import URL

from trace_shrink import HarEntry, HarReader

# --- Fixtures ---


# Fixture for the path to the real HAR file
@pytest.fixture(scope="module")  # Use module scope as the file doesn't change
def real_har_file_path() -> Path:
    path = Path(__file__).parent / "archives" / "export-proxyman.har"
    if not path.exists():
        pytest.skip(f"Real HAR file not found: {path}")
    return path


# Fixture to create a HarReader instance from the real file
@pytest.fixture(scope="module")
def har_reader(real_har_file_path: Path) -> HarReader:
    return HarReader(str(real_har_file_path))


# Fixture for creating a dummy HAR file (useful for specific error cases)
@pytest.fixture(scope="function")
def dummy_har_file(tmp_path: Path):
    def _create_dummy(content: Any):
        path = tmp_path / "dummy.har"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(content, f)
        except Exception as e:
            # Handle cases where content itself isn't JSON serializable for test setup
            path.write_text(str(content), encoding="utf-8")
        return str(path)

    return _create_dummy


# --- Test Initialization ---


def test_har_reader_init_success(har_reader: HarReader, real_har_file_path: Path):
    """Test successful initialization with a real HAR file."""
    assert har_reader.har_file_path == str(real_har_file_path)
    assert har_reader._raw_har_data is not None
    assert "log" in har_reader._raw_har_data
    assert len(har_reader._entries) > 0
    assert isinstance(har_reader._entries[0], HarEntry)


def test_har_reader_init_file_not_found():
    """Test initialization with a non-existent file."""
    with pytest.raises(FileNotFoundError):
        HarReader("non_existent_file.har")


def test_har_reader_init_invalid_json(dummy_har_file):
    """Test initialization with invalid JSON content."""
    # Use unambiguously invalid JSON
    invalid_json_path = dummy_har_file("{invalid structure}")
    with pytest.raises(ValueError, match="Invalid JSON"):
        HarReader(invalid_json_path)


def test_har_reader_init_not_har_format_no_log(dummy_har_file):
    """Test initialization with valid JSON but missing 'log' key."""
    not_har_path = dummy_har_file({"some_other_key": "value"})
    with pytest.raises(ValueError, match="Invalid HAR format: 'log' object not found"):
        HarReader(not_har_path)


def test_har_reader_init_not_har_format_no_entries(dummy_har_file):
    """Test initialization with valid JSON, 'log' key, but missing 'entries' list."""
    no_entries_path = dummy_har_file(
        {"log": {"version": "1.2", "creator": {}}}
    )  # No 'entries'
    with pytest.raises(ValueError, match="Invalid HAR format: 'log.entries' not found"):
        HarReader(no_entries_path)


def test_har_reader_init_entries_not_list(dummy_har_file):
    """Test initialization where 'log.entries' is not a list."""
    entries_not_list_path = dummy_har_file({"log": {"entries": {"key": "value"}}})
    with pytest.raises(
        ValueError, match="Invalid HAR format: 'log.entries' is not a list"
    ):
        HarReader(entries_not_list_path)


# --- Test Reader Methods ---


def test_har_reader_len(har_reader: HarReader):
    """Test the __len__ method."""
    assert len(har_reader) == 17


def test_har_reader_iter(har_reader: HarReader):
    """Test iterating over the reader."""
    count = 0
    for entry in har_reader:
        assert isinstance(entry, HarEntry)
        count += 1
    assert count == len(har_reader)


def test_har_reader_list_entries(har_reader: HarReader):
    """Test the list_entries method."""
    entries_list = har_reader.entries
    assert isinstance(entries_list, list)
    assert len(entries_list) == len(har_reader)
    if entries_list:
        assert isinstance(entries_list[0], HarEntry)


def test_har_reader_get_entries_for_url(har_reader: HarReader):
    """Test filtering entries by URL pattern."""
    # Find entries with 'masterp_360p' in the URL (expecting HLS playlist)
    hls_entries = har_reader.get_entries_for_partial_url("masterp_360p")
    assert len(hls_entries) > 0  # Expect at least one match in the sample file
    for entry in hls_entries:
        assert isinstance(entry, HarEntry)
        assert "masterp_360p" in str(entry.request.url)

    # Find entries for a specific host (using regex)
    # Note: Host matching might depend on case sensitivity of regex
    bpk_entries = har_reader.get_entries_for_partial_url("https://stream.broadpeak.io")
    assert len(bpk_entries) > 0  # Expect matches
    for entry in bpk_entries:
        assert entry.request.url.host == "stream.broadpeak.io"

    # Test no match
    no_match_entries = har_reader.get_entries_for_partial_url("nonexistentdomain")
    assert len(no_match_entries) == 0


# --- Test Properties of Entries Read from Real File ---


def test_har_entry_properties_from_reader(har_reader: HarReader):
    """Test properties of a specific entry loaded via the reader."""
    hls_entries = har_reader.get_entries_for_partial_url("masterp_360p@1.m3u8")
    assert len(hls_entries) >= 1
    entry = hls_entries[0]

    assert isinstance(entry, HarEntry)
    assert entry.request.method == "GET"
    assert isinstance(entry.request.url, URL)
    assert "masterp_360p@1.m3u8" in str(entry.request.url)
    assert entry.response.status_code == 200
    assert entry.response.mime_type == "application/x-mpegURL"

    # Check timings: allow for None (if timing value was -1 in HAR)
    start_time = entry.timeline.request_start
    assert start_time is not None

    response_end = entry.timeline.response_end
    assert response_end is not None
    assert response_end > start_time

    # Check body (should be HLS content)
    body_text = entry.response.body.text
    assert body_text is not None
    assert "#EXTM3U" in body_text
    assert entry.response.body.raw_size > 0
    assert entry.response.body.compressed_size > 0
