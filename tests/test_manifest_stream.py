from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from trace_shrink.manifest_stream import ManifestStream
from trace_shrink.trace_entry import TraceEntry


# Helper to create mock TraceEntry objects with specific timestamps
def create_mock_entry(timestamp: datetime) -> Mock:
    entry = Mock(spec=TraceEntry)
    entry.timeline = Mock()
    entry.timeline.request_start = timestamp
    entry.id = f"entry_{timestamp.isoformat()}"  # Add a unique ID for easier debugging
    return entry


# A more comprehensive fixture for testing various scenarios
@pytest.fixture
def stream() -> ManifestStream:
    start_time = datetime(2023, 1, 1, 12, 0, 0)
    entries = [
        create_mock_entry(start_time),  # 12:00:00
        create_mock_entry(start_time + timedelta(seconds=2)),  # 12:00:02
        create_mock_entry(start_time + timedelta(seconds=4)),  # 12:00:04
        create_mock_entry(start_time + timedelta(seconds=6)),  # 12:00:06
        create_mock_entry(start_time + timedelta(seconds=8)),  # 12:00:08
        create_mock_entry(start_time + timedelta(seconds=10)),  # 12:00:10
    ]
    return ManifestStream(entries)


# === Basic Initialization Tests ===
def test_initialization_with_empty_list():
    with pytest.raises(ValueError):
        ManifestStream([])


def test_initialization_sorts_entries():
    start_time = datetime(2023, 1, 1, 12, 0, 0)
    shuffled_entries = [
        create_mock_entry(start_time + timedelta(seconds=4)),
        create_mock_entry(start_time),
        create_mock_entry(start_time + timedelta(seconds=2)),
    ]
    stream = ManifestStream(shuffled_entries)
    assert stream.timestamps[0] < stream.timestamps[1] < stream.timestamps[2]


# === Tests for Tolerance Logic (Primary Search) ===
def test_tolerance_finds_single_exact_match(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 4)
    found = stream.find_entry_by_time(target_time, tolerance=0.5)
    assert found.timeline.request_start == target_time


def test_tolerance_finds_closest_among_multiple_matches(stream: ManifestStream):
    # Target 12:00:05. Tolerance of 1.5s includes :04 and :06.
    # 12:00:04 is 1s away, 12:00:06 is 1s away (tie, returns later)
    # Let's make target 12:00:04.9, it's closer to :04
    target_time = datetime(2023, 1, 1, 12, 0, 4, 900000)
    found = stream.find_entry_by_time(target_time, tolerance=1.5)
    # Should be 12:00:04, which is 0.9s away, not 12:00:06 (1.1s away)
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 4)


def test_tolerance_finds_nothing_so_falls_back_to_position(stream: ManifestStream):
    # Target 12:00:05, tolerance 0.1s. Nothing is in [12:00:04.9, 12:00:05.1]
    target_time = datetime(2023, 1, 1, 12, 0, 5)
    # Since tolerance fails, it should use position="nearest" (default)
    found = stream.find_entry_by_time(target_time, tolerance=0.1)
    # Nearest to 12:00:05 is 12:00:04 or 12:00:06, tie-breaks to later
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 6)


# === Tests for Position Logic (Fallback Search) ===


# --- Position: 'nearest' ---
def test_position_nearest_midpoint(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5)
    found = stream.find_entry_by_time(target_time, position="nearest")
    # Midpoint between :04 and :06, should return the later one
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 6)


def test_position_nearest_before_all(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 11, 59, 59)
    found = stream.find_entry_by_time(target_time, position="nearest")
    assert found == stream.entries[0]


def test_position_nearest_after_all(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 15)
    found = stream.find_entry_by_time(target_time, position="nearest")
    assert found == stream.entries[-1]


# --- Position: 'after' ---
def test_position_after_finds_next_available(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5)  # Between :04 and :06
    found = stream.find_entry_by_time(target_time, position="after")
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 6)


def test_position_after_on_exact_match_finds_next(stream: ManifestStream):
    # Target is exactly 12:00:04, should find 12:00:06
    target_time = datetime(2023, 1, 1, 12, 0, 4)
    found = stream.find_entry_by_time(target_time, position="after")
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 6)


def test_position_after_last_entry_returns_none(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 10)  # Exact match with last
    found = stream.find_entry_by_time(target_time, position="after")
    assert found is None


# --- Position: 'before' ---
def test_position_before_finds_previous_available(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 5)  # Between :04 and :06
    found = stream.find_entry_by_time(target_time, position="before")
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 4)


def test_position_before_on_exact_match_finds_previous(stream: ManifestStream):
    # Target is exactly 12:00:04, should find 12:00:02
    target_time = datetime(2023, 1, 1, 12, 0, 4)
    found = stream.find_entry_by_time(target_time, position="before")
    assert found.timeline.request_start == datetime(2023, 1, 1, 12, 0, 2)


def test_position_before_first_entry_returns_none(stream: ManifestStream):
    target_time = datetime(2023, 1, 1, 12, 0, 0)  # Exact match with first
    found = stream.find_entry_by_time(target_time, position="before")
    assert found is None
