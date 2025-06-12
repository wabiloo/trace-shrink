import json
import zipfile
from pathlib import Path

import pytest
from yarl import URL  # For URL assertions

# Updated imports
from trace_shrink import ProxymanLogV2Entry, ProxymanLogV2Reader

# Define the structure and content for a dummy log file
# Adjusted to include more fields for comprehensive testing and ensure IDs are consistent.
# The 'id' in the JSON content will be used by ProxymanLogV2Entry.id
# The id in the filename (e.g., 'file-id-123') is used by the reader for indexing if JSON 'id' is missing.
DUMMY_LOG_ENTRIES = {
    "request_0_file-id-123": {
        "request": {
            "host": "example.com",
            "uri": "/path1",
            "scheme": "http",
            "fullPath": "http://example.com/path1",
            "method": {"name": "GET"},
            "header": {"entries": []},
        },
        "response": {
            "status": {"code": 200},
            "header": {"entries": []},
            "bodySize": 0,
            "bodyEncodedSize": 0,
        },
        "id": "123",
    },
    "request_1_file-id-456": {
        "request": {
            "host": "another.org",
            "uri": "/path2?q=abc",
            "scheme": "https",
            "fullPath": "https://another.org/path2?q=abc",
            "method": {"name": "POST"},
            "header": {"entries": []},
        },
        "response": {
            "status": {"code": 201},
            "header": {"entries": []},
            "bodySize": 10,
            "bodyEncodedSize": 10,
        },
        "id": "456",
    },
    "request_2_file-id-789": {
        "request": {
            "host": "example.com",
            "uri": "/other",
            "scheme": "http",
            "fullPath": "http://example.com/other",
            "method": {"name": "GET"},
            "header": {"entries": []},
        },
        "response": {
            "status": {"code": 404},
            "header": {"entries": []},
            "bodySize": 0,
            "bodyEncodedSize": 0,
        },
        "id": "789",
    },
    "not_a_request_file": "some text data",
    # Entry with malformed JSON content for the value part
    "request_99_malformed-json-id": '{"key": "value",',
    # Entry where the file content is valid JSON, but misses critical 'request' key for index metadata
    "request_3_missing-keys-id": {
        "foo": "bar",  # No "request" object here, so host/uri in index will be None
        "id": "json-id-missing-keys",
    },
    # Entry with host=None in its content
    "request_4_null-host-id": {
        "request": {
            "host": None,
            "uri": "/path_no_host",
            "scheme": "http",
            "fullPath": "/path_no_host",  # fullPath might be just the path
            "method": {"name": "GET"},
            "header": {"entries": []},
        },
        "response": {
            "status": {"code": 200},
            "header": {"entries": []},
            "bodySize": 0,
            "bodyEncodedSize": 0,
        },
        "id": "json-id-null-host",
    },
}


@pytest.fixture(scope="function")
def dummy_log_file(tmp_path: Path):
    log_path = tmp_path / "test.proxymanlogv2"
    with zipfile.ZipFile(log_path, "w") as zf:
        for name, content in DUMMY_LOG_ENTRIES.items():
            if isinstance(content, dict):
                zf.writestr(name, json.dumps(content))
            elif isinstance(content, str):
                zf.writestr(name, content)
    yield str(log_path)


@pytest.fixture(scope="function")
def non_zip_file(tmp_path: Path):
    file_path = tmp_path / "not_a_zip.txt"
    file_path.write_text("This is not a zip file.")
    return str(file_path)


# --- Test Initialization ---


def test_init_success(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    assert reader.log_file_path == dummy_log_file
    index = reader.get_index()
    assert len(index) == 6  # Corrected to 6 based on DUMMY_LOG_ENTRIES
    assert "request_0_file-id-123" in index
    assert "request_1_file-id-456" in index
    assert "request_2_file-id-789" in index
    assert "request_3_missing-keys-id" in index
    assert "request_99_malformed-json-id" in index
    assert "request_4_null-host-id" in index
    assert "not_a_request_file" not in index


def test_init_file_not_found():
    with pytest.raises(FileNotFoundError):
        ProxymanLogV2Reader("non_existent_log_file.proxymanlogv2")


def test_init_not_a_zip(non_zip_file):
    # Updated error message to match the one in ProxymanLogV2Reader
    with pytest.raises(
        ValueError, match=r"File is not a valid Proxyman log \(zip archive\)"
    ):
        ProxymanLogV2Reader(non_zip_file)


# --- Test Index Content ---


def test_index_content(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    index = reader.get_index()

    entry0 = index.get("request_0_file-id-123")
    assert entry0 is not None
    assert entry0["id"] == "file-id-123"
    assert entry0["index"] == 0
    assert entry0["host"] == "example.com"
    assert entry0["uri"] == "/path1"

    entry1 = index.get("request_1_file-id-456")
    assert entry1 is not None
    assert entry1["id"] == "file-id-456"
    assert entry1["index"] == 1
    assert entry1["host"] == "another.org"
    assert entry1["uri"] == "/path2?q=abc"

    entry3 = index.get("request_3_missing-keys-id")
    assert entry3 is not None
    assert entry3["id"] == "missing-keys-id"
    assert entry3["index"] == 3
    assert entry3["host"] is None
    assert entry3["uri"] is None

    entry99 = index.get("request_99_malformed-json-id")
    assert entry99 is not None
    assert entry99["id"] == "malformed-json-id"
    assert entry99["index"] == 99
    assert entry99["host"] is None
    assert entry99["uri"] is None

    entry4 = index.get("request_4_null-host-id")
    assert entry4 is not None
    assert entry4["id"] == "null-host-id"
    assert entry4["index"] == 4
    assert entry4["host"] is None
    assert entry4["uri"] == "/path_no_host"


# --- Test Listing and Basic Filtering ---


def test_list_entries_sorted(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    entries = reader.entries
    entry_ids = [e.id for e in entries]
    assert entry_ids == [
        "123",
        "456",
        "789",
        "json-id-missing-keys",
        "json-id-null-host",
    ]


def test_list_entries_by_host_sorting_and_filtering(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    example_entries = reader.list_entries_by_host("example.com")
    assert example_entries == ["request_0_file-id-123", "request_2_file-id-789"]
    example_entries_upper = reader.list_entries_by_host("EXAMPLE.COM")
    assert example_entries_upper == ["request_0_file-id-123", "request_2_file-id-789"]
    another_entries = reader.list_entries_by_host("another.org")
    assert another_entries == ["request_1_file-id-456"]
    no_match_entries = reader.list_entries_by_host("nonexistent.com")
    assert no_match_entries == []
    null_host_entries = reader.list_entries_by_host(None)
    assert null_host_entries == [
        "request_3_missing-keys-id",
        "request_4_null-host-id",
        "request_99_malformed-json-id",
    ]


# --- Test Entry Object Retrieval and Properties ---


def test_get_entry_success(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    entry_obj = reader._parse_entry(entry_filename="request_1_file-id-456")

    assert entry_obj is not None
    assert isinstance(entry_obj, ProxymanLogV2Entry)
    assert entry_obj._entry_name == "request_1_file-id-456"
    # ProxymanLogV2Entry.id uses the 'id' from JSON content if available
    assert entry_obj.id == "456"
    assert str(entry_obj.request.url) == "https://another.org/path2?q=abc"
    assert entry_obj.request.method == "POST"
    assert entry_obj.response.status_code == 201


def test_get_entry_not_found_in_index(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    entry_obj = reader._parse_entry(entry_filename="request_999_xyz")
    assert entry_obj is None


def test_get_entry_malformed_json_content(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    # This entry has a filename that matches pattern, but its content is bad JSON
    entry_obj = reader._parse_entry(entry_filename="request_99_malformed-json-id")
    # get_entry should return None if JSON loading of the content fails
    assert entry_obj is None


def test_get_entry_missing_keys_in_content(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    # This entry has valid JSON, but might miss keys ProxymanLogV2Entry expects for its properties
    # However, ProxymanLogV2Entry is designed to be somewhat robust to missing keys (e.g. defaulting, returning None)
    entry_obj = reader._parse_entry(entry_filename="request_3_missing-keys-id")
    assert entry_obj is not None  # Should still load the entry object
    assert isinstance(entry_obj, ProxymanLogV2Entry)
    assert entry_obj.id == "json-id-missing-keys"
    # Request URL might be minimal or default if parts are missing
    assert (
        str(entry_obj.request.url) == "/"
    )  # default path if host/scheme is missing from request data
    assert entry_obj.request.method == "GET"  # Default if not in data
    assert entry_obj.response.status_code == 0  # Default if not in data


# --- Test Iterating and Retrieving Multiple Entries ---


def test_get_entries_by_host_yielding_objects(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)

    example_host_iter = reader.get_entries_by_host("example.com")
    example_entries = list(example_host_iter)

    assert len(example_entries) == 2
    assert isinstance(example_entries[0], ProxymanLogV2Entry)
    assert isinstance(example_entries[1], ProxymanLogV2Entry)
    entry_ids = sorted([e.id for e in example_entries])
    assert entry_ids == sorted(["123", "789"])
    assert example_entries[0].id == "123"
    assert str(example_entries[0].request.url) == "http://example.com/path1"
    assert example_entries[1].id == "789"
    assert str(example_entries[1].request.url) == "http://example.com/other"

    no_match_iter = reader.get_entries_by_host("nonexistent.com")
    assert list(no_match_iter) == []

    null_host_iter = reader.get_entries_by_host(None)
    null_host_entries = list(null_host_iter)
    # Corrected expectation: only 2 entries are successfully loaded and yielded
    # because request_99_malformed-json-id will not be parsed by get_entry()
    assert len(null_host_entries) == 2
    null_host_ids = sorted([e.id for e in null_host_entries])
    # This expectation remains correct as it only includes the successfully loaded ones
    expected_null_ids = sorted(["json-id-missing-keys", "json-id-null-host"])
    assert null_host_ids == expected_null_ids


# --- Test Dunder Methods __len__ and __iter__ ---
def test_len_method(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    assert len(reader) == 6  # Total number of indexed entries by filename


def test_iter_method(dummy_log_file):
    reader = ProxymanLogV2Reader(dummy_log_file)
    iterated_entries = list(reader)  # Calls __iter__ then get_entry for each
    # Should yield only successfully loaded entries
    # request_99_malformed-json-id will fail get_entry
    assert len(iterated_entries) == 5

    iterated_ids = sorted([entry.id for entry in iterated_entries])
    expected_ids = sorted(
        [
            "123",
            "456",
            "789",
            "json-id-missing-keys",
            "json-id-null-host",
        ]
    )
    assert iterated_ids == expected_ids
    for entry in iterated_entries:
        assert isinstance(entry, ProxymanLogV2Entry)


# --- Test with Real Log File  ---

REAL_LOG_FILE_PATH = (
    Path(__file__).parent / "archives" / "export-proxyman.proxymanlogv2"
)


@pytest.mark.skipif(
    not REAL_LOG_FILE_PATH.exists(),
    reason=f"Real log file not found: {REAL_LOG_FILE_PATH}",
)
def test_read_real_log_file():
    log_path_str = str(REAL_LOG_FILE_PATH)
    print(f"\nAttempting to read real log file: {log_path_str}")
    reader = ProxymanLogV2Reader(log_path_str)

    assert reader.log_file_path == log_path_str
    index = reader.get_index()
    assert isinstance(index, dict)
    assert len(index) > 0, "Index should not be empty for the real log file."
    print(f"Real log file indexed {len(index)} entries.")

    entries = reader.entries
    assert isinstance(entries, list)
    assert len(entries) > 0
    print(f"First 5 entry filenames found: {entries[:5]}")

    if entries:
        first_entry_obj = entries[0]

        assert first_entry_obj is not None, (
            f"Should be able to retrieve entry object for {first_entry_obj}"
        )
        assert isinstance(first_entry_obj, ProxymanLogV2Entry), (
            f"Retrieved object for {first_entry_obj} should be a ProxymanLogV2Entry"
        )

        # Check some basic properties of the retrieved real entry
        assert first_entry_obj.id is not None
        assert first_entry_obj.request.method is not None
        assert isinstance(first_entry_obj.request.url, URL)
        assert first_entry_obj.response.status_code is not None

        print(
            f"Successfully retrieved ProxymanLogV2Entry for {first_entry_obj}. ID: {first_entry_obj.id}, URL: {first_entry_obj.request.url}"
        )

    # Test iteration over a few real entries
    print("\nIterating over first 3 real entries (if available):")
    iter_count = 0
    for entry in reader:
        if iter_count < 3:
            assert isinstance(entry, ProxymanLogV2Entry)
            print(
                f"  Iterated: {entry.id} - {entry.request.method} {entry.request.url} -> {entry.response.status_code}"
            )
            iter_count += 1
        else:
            break
    assert iter_count > 0 if len(reader) > 0 else iter_count == 0

    # Test get_entries_for_url with a common pattern on the real log
    # Example: Find manifest/playlist files (m3u8, mpd)
    print("\nSearching for .m3u8 or .mpd in URLs (real log):")
    manifest_entries = reader.get_entries_for_url(r"(\.m3u8|\.mpd)")
    print(f"Found {len(manifest_entries)} potential manifest entries.")
    for entry in manifest_entries[:5]:  # Print first 5 found
        print(f"  Manifest entry: {entry.id} - {entry.request.url}")
    # No strict assertion on count, as it depends on the real log content
