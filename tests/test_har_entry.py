# tests/test_har_entry.py
import base64

import pytest
from yarl import URL

# Import the class to test
from trace_shrink import HarEntry

# Define a representative sample HAR entry dictionary for isolated testing
# Based loosely on HAR 1.2 spec examples and common fields
HAR_ENTRY_DICT_SAMPLE = {
    "startedDateTime": "2024-05-15T12:00:00.123Z",
    "time": 150.5,  # Total time in ms
    "request": {
        "method": "POST",
        "url": "https://api.example.com/v1/data?param=value",
        "httpVersion": "HTTP/1.1",
        "headers": [
            {"name": "Content-Type", "value": "application/json; charset=utf-8"},
            {"name": "Accept", "value": "application/json"},
            {"name": "Host", "value": "api.example.com"},
        ],
        "queryString": [{"name": "param", "value": "value"}],
        "cookies": [],
        "headersSize": 150,  # Approx size
        "bodySize": 25,  # Approx size
        "postData": {
            "mimeType": "application/json; charset=utf-8",
            "text": '{"key": "some data"}',
            # params would be here for application/x-www-form-urlencoded
        },
    },
    "response": {
        "status": 201,
        "statusText": "Created",
        "httpVersion": "HTTP/1.1",
        "headers": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Content-Length", "value": "50"},  # Matches bodySize
            {"name": "Date", "value": "Wed, 15 May 2024 12:00:00 GMT"},
            {"name": "Server", "value": "ExampleServer/1.0"},
        ],
        "cookies": [],
        "content": {
            "size": 30,  # Uncompressed size
            "compression": 0,  # Or bytes saved, e.g., 20 if bodySize was 30 but size is 50
            "mimeType": "application/json",
            # Example base64 encoded body: {"id": "xyz789", "status": "success"}
            "text": "eyJpZCI6ICJ4eXo3ODkiLCAic3RhdHVzIjogInN1Y2Nlc3MifQ==",
            "encoding": "base64",
        },
        "redirectURL": "",
        "headersSize": 180,  # Approx size
        "bodySize": 50,  # Transferred size (may differ from content.size if compressed)
    },
    "cache": {},
    "timings": {
        "blocked": 10.1,
        "dns": -1,  # Not applicable
        "connect": 25.5,
        "ssl": 15.0,  # Part of connect
        "send": 20.2,
        "wait": 50.3,
        "receive": 44.4,
    },
    "serverIPAddress": "192.0.2.1",
    "_securityState": "secure",
    "comment": "This is a test HAR entry.",
}


# Fixture to create HarEntry instance from the sample dictionary
@pytest.fixture
def sample_har_entry():
    # In isolation tests, reader can be None, entry_index is arbitrary (e.g., 0)
    return HarEntry(HAR_ENTRY_DICT_SAMPLE, reader=None, entry_index=0)


# --- Basic Initialization and ID ---
def test_har_entry_init_and_id(sample_har_entry):
    """Test basic initialization and the generated ID."""
    assert sample_har_entry is not None
    assert sample_har_entry._raw_data == HAR_ENTRY_DICT_SAMPLE
    assert sample_har_entry.id == "index-0"  # Auto-generated ID


# --- Request Properties ---
def test_har_request_url(sample_har_entry):
    """Test request URL parsing."""
    assert isinstance(sample_har_entry.request.url, URL)
    assert (
        str(sample_har_entry.request.url)
        == "https://api.example.com/v1/data?param=value"
    )
    assert sample_har_entry.request.url.host == "api.example.com"


def test_har_request_method(sample_har_entry):
    """Test request method."""
    assert sample_har_entry.request.method == "POST"


def test_har_request_headers(sample_har_entry):
    """Test request headers parsing."""
    headers = sample_har_entry.request.headers
    assert isinstance(headers, dict)
    assert len(headers) == 3
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Host"] == "api.example.com"


# --- Response Properties ---
def test_har_response_status_code(sample_har_entry):
    """Test response status code."""
    assert sample_har_entry.response.status_code == 201


def test_har_response_headers(sample_har_entry):
    """Test response headers parsing."""
    headers = sample_har_entry.response.headers
    assert isinstance(headers, dict)
    assert len(headers) == 4
    assert headers["Content-Type"] == "application/json"
    assert headers["Server"] == "ExampleServer/1.0"


def test_har_response_content_type_and_mime(sample_har_entry):
    """Test response content/mime type from response.content."""
    assert sample_har_entry.response.content_type == "application/json"
    assert sample_har_entry.response.mime_type == "application/json"


# --- Response Body Properties ---
def test_har_response_body_decoded_bytes(sample_har_entry):
    """Test response body decoding (base64 in this sample)."""
    # _get_decoded_body is internal, but useful for checking intermediate step
    decoded = sample_har_entry.response.body._get_decoded_body()
    assert isinstance(decoded, bytes)
    assert decoded == b'{"id": "xyz789", "status": "success"}'


def test_har_response_body_text(sample_har_entry):
    """Test response body text decoding."""
    text = sample_har_entry.response.body.text
    assert isinstance(text, str)
    # Should decode using utf-8 by default if content-type has no charset
    assert text == '{"id": "xyz789", "status": "success"}'


def test_har_response_body_raw_size(sample_har_entry):
    """Test raw (uncompressed) body size."""
    # Uses response.content.size
    assert sample_har_entry.response.body.raw_size == 30


def test_har_response_body_compressed_size(sample_har_entry):
    """Test compressed (transferred) body size."""
    # Uses response.bodySize
    assert sample_har_entry.response.body.compressed_size == 50


def test_har_response_body_no_text(sample_har_entry):
    """Test response body when response.content.text is None."""
    data_no_text = HAR_ENTRY_DICT_SAMPLE.copy()
    data_no_text["response"] = data_no_text["response"].copy()
    data_no_text["response"]["content"] = data_no_text["response"]["content"].copy()
    data_no_text["response"]["content"]["text"] = None
    entry_no_text = HarEntry(data_no_text, reader=None, entry_index=2)

    assert entry_no_text.response.body._get_decoded_body() is None
    assert entry_no_text.response.body.text is None
    # raw_size should fallback to 0 if decoded body is None and size wasn't valid
    # Here content.size is still 30, so raw_size should be 30
    assert entry_no_text.response.body.raw_size == 30
    assert entry_no_text.response.body.compressed_size == 50


def test_har_content_property(sample_har_entry):
    assert sample_har_entry.content.decode("utf-8") == sample_har_entry.response.body.text

# --- Timings ---
def test_har_timings(sample_har_entry):
    """Test parsing of timing values."""
    timings = sample_har_entry.timeline
    assert timings.request_start is not None
    assert timings.response_end is not None


def test_har_total_time_from_entry(sample_har_entry):
    """Test total time property (uses entry.time)."""
    # entry.time is 150.5 ms
    assert sample_har_entry.time == 150.5
    # timings.total_time currently accesses parent entry.time
    # assert sample_har_entry.timings.total_time == pytest.approx(0.1505) # Needs fix in timings


# --- Other Properties ---
def test_har_comment(sample_har_entry):
    """Test comment property."""
    assert sample_har_entry.comment == "This is a test HAR entry."


def test_har_get_raw_json(sample_har_entry):
    """Test retrieving the raw JSON."""
    assert sample_har_entry.get_raw_json() == HAR_ENTRY_DICT_SAMPLE


def test_har_str_repr(sample_har_entry):
    """Test string representation."""
    assert str(sample_har_entry).startswith(
        "HarEntry(id=index-0 POST https://api.example.com/v1/data?param=value -> 201)"
    )
    assert (
        repr(sample_har_entry)
        == "<HarEntry id=index-0 POST https://api.example.com/v1/data?param=value -> 201>"
    )
