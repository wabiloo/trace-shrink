from datetime import datetime, timedelta, timezone

import pytest
import yarl

from trace_shrink.formats import Format
from trace_shrink.manifest_stream import ManifestStream


# Minimal test classes to simulate TraceEntry and sub-objects
class TestTimeline:
    def __init__(self, request_start):
        self.request_start = request_start


class TestRequest:
    def __init__(self, url):
        self.url = url


class TestResponse:
    def __init__(self, headers):
        self.headers = headers


class TestTraceEntry:
    def __init__(self, timestamp):
        self.timeline = TestTimeline(timestamp)
        self.request = TestRequest(
            yarl.URL(f"https://example.com/manifest_{timestamp:%H%M%S}.m3u8")
        )
        self.response = TestResponse({"content-type": "application/vnd.apple.mpegurl"})
        self.id = f"entry_{timestamp.isoformat()}"


# Helper to create mock TraceEntry objects with specific timestamps
def create_mock_entry(timestamp: datetime):
    return TestTraceEntry(timestamp)


# A more comprehensive fixture for testing various scenarios
@pytest.fixture
def stream() -> ManifestStream:
    start_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        create_mock_entry(start_time),
        create_mock_entry(start_time + timedelta(seconds=2)),
        create_mock_entry(start_time + timedelta(seconds=4)),
        create_mock_entry(start_time + timedelta(seconds=6)),
        create_mock_entry(start_time + timedelta(seconds=8)),
        create_mock_entry(start_time + timedelta(seconds=10)),
    ]
    return ManifestStream(entries)


# === Basic Initialization Tests ===
def test_initialization_with_empty_list():
    with pytest.raises(
        ValueError,
        match="Cannot create a ManifestStream with an empty list of entries.",
    ):
        ManifestStream([])


def test_initialization_sorts_entries():
    start_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    shuffled_entries = [
        create_mock_entry(start_time + timedelta(seconds=4)),
        create_mock_entry(start_time),
        create_mock_entry(start_time + timedelta(seconds=2)),
    ]
    stream = ManifestStream(shuffled_entries)
    assert stream.timestamps[0] < stream.timestamps[1] < stream.timestamps[2]


# === Tests for Tolerance Logic (Primary Search) ===
def test_tolerance_finds_single_exact_match(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 4, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, tolerance=0.5)
    assert found.timeline.request_start == target_time


def test_tolerance_finds_closest_among_multiple_matches(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 4, 900000, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, tolerance=1.5)
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 4, tzinfo=timezone.utc
    )


def test_tolerance_finds_nothing_so_falls_back_to_position(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, tolerance=0.1)
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 6, tzinfo=timezone.utc
    )


# === Tests for Position Logic (Fallback Search) ===


# --- Position: 'nearest' ---
def test_position_nearest_midpoint(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="nearest")
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 6, tzinfo=timezone.utc
    )


def test_position_nearest_before_all(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 11, 59, 59, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="nearest")
    assert found == stream.entries[0]


def test_position_nearest_after_all(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 15, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="nearest")
    assert found == stream.entries[-1]


# --- Position: 'after' ---
def test_position_after_finds_next_available(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="after")
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 6, tzinfo=timezone.utc
    )


def test_position_after_on_exact_match_finds_next(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 4, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="after")
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 6, tzinfo=timezone.utc
    )


def test_position_after_last_entry_returns_none(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="after")
    assert found is None


# --- Position: 'before' ---
def test_position_before_finds_previous_available(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="before")
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 4, tzinfo=timezone.utc
    )


def test_position_before_on_exact_match_finds_previous(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 4, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="before")
    assert found.timeline.request_start == datetime(
        2023, 1, 1, 12, 0, 2, tzinfo=timezone.utc
    )


def test_position_before_first_entry_returns_none(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    found = stream.find_entry_by_time(target_time, position="before")
    assert found is None


# === Test for .format property ===
@pytest.mark.parametrize(
    "url, mime_type, expected_format",
    [
        # HLS detection
        ("http://test.com/master.m3u8", "application/vnd.apple.mpegurl", Format.HLS),
        ("http://test.com/other.m3u8", "application/x-mpegurl", Format.HLS),
        ("http://test.com/playlist.m3u8", "application/octet-stream", Format.HLS),
        # by extension
        # DASH detection
        ("http://test.com/manifest.mpd", "application/dash+xml", Format.DASH),
        ("http://test.com/init.mpd", "application/octet-stream", Format.DASH),
        # by extension
        # No ABR format
        ("http://test.com/video.ts", "video/mp2t", None),
        ("http://test.com/data.json", "application/json", None),
        ("http://test.com/text", "text/plain", None),
    ],
)
def test_manifest_stream_format_property(url, mime_type, expected_format):
    """Tests that the .format property is correctly determined from the first entry."""
    # Create a mock entry with the specified URL and MIME type.
    # The existing helper creates a very specific type of entry, so we'll just modify it.
    entry = create_mock_entry(datetime.now(timezone.utc))
    entry.request.url = yarl.URL(url)
    entry.response.headers = {"content-type": mime_type}

    stream = ManifestStream([entry])

    assert stream.format == expected_format
