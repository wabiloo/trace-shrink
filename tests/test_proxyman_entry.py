import base64

import pytest
from yarl import URL

# Updated import to use the new class from the new package structure
from trace_shrink import ProxymanLogV2Entry, ProxymanLogV2Reader

# Sample data (remains largely the same structure for raw input)
SAMPLE_ENTRY_DATA = {
    "request": {
        "host": "stream.broadpeak.io",
        "uri": "/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=SERVICEID",
        "scheme": "https",  
        "port": 443,  
        "header": {
            "entries": [
                {"key": {"name": "Host"}, "value": "stream.broadpeak.io"},
                {"key": {"name": "User-Agent"}, "value": "Mozilla/5.0 TestAgent"},
                {"key": {"name": "Accept"}, "value": "*/*"},
            ]
        },
        "method": {"name": "GET"},
        "fullPath": "https://stream.broadpeak.io/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=SERVICEID",
        "bodyData": None,
    },
    "response": {
        "status": {"code": 200, "phrase": "OK"},
        "header": {
            "entries": [
                {
                    "key": {"name": "Content-Type"},
                    "value": "application/vnd.apple.mpegurl; charset=utf-8",
                },
                {"key": {"name": "Date"}, "value": "Mon, 28 Apr 2025 09:01:16 GMT"},
                {
                    "key": {"name": "Content-Length"},
                    "value": "105",
                },
            ]
        },
        "bodyData": "I0VYVE0zVQojRVhULVgtVkVSU0lPTjo0CiNFWFRJTkY6NCwgbm8gZGVzYwpyZXNvdXJjZS0xLnRzCiNFWFRJTkY6NCwgbm8gZGVzYwpyZXNvdXJjZS0yLnRzCiNFWFQtWC1FTkRMSVNU",
        "bodySize": 105,
        "bodyEncodedSize": 105,
    },
    "id": "test-id-86",  # Proxyman's top-level ID for the entry
    "notes": "This is a sample entry comment.",
    "timing": {  # Basic timing data for placeholder tests
        "startDate": "2024-05-15T10:00:00.000Z",
        "endDate": "2024-05-15T10:00:01.500Z",
    },
}

NO_BODY_DATA = {
    "request": {
        "host": "test.com",
        "uri": "/",
        "header": {"entries": []},
        "method": {"name": "GET"},
        "bodyData": None,
        "fullPath": "http://test.com/",
    },
    "response": {
        "status": {"code": 204},
        "header": {"entries": []},
        "bodyData": None,
        "bodySize": 0,
        "bodyEncodedSize": 0,
    },
    "id": "test-id-100",
}

INVALID_BODY_DATA = {
    "request": {
        "host": "invalid.com",
        "uri": "/",
        "header": {"entries": []},
        "method": {"name": "GET"},
        "bodyData": None,
        "fullPath": "http://invalid.com/",
    },
    "response": {
        "status": {"code": 500},
        "header": {"entries": []},
        "bodyData": "this is not base64!@#$",
        "bodySize": 0,
        "bodyEncodedSize": 0,
    },
    "id": "test-id-101",
}


# For testing, the reader can be None if the entry doesn't interact with it for these tests.
@pytest.fixture
def sample_entry():
    return ProxymanLogV2Entry("request_0_test-id-86", SAMPLE_ENTRY_DATA, reader=None)


@pytest.fixture
def no_body_entry():
    return ProxymanLogV2Entry("request_1_test-id-100", NO_BODY_DATA, reader=None)


@pytest.fixture
def invalid_body_entry():
    return ProxymanLogV2Entry("request_2_test-id-101", INVALID_BODY_DATA, reader=None)


def test_init(sample_entry):
    assert sample_entry._raw_data == SAMPLE_ENTRY_DATA
    assert sample_entry._entry_name == "request_0_test-id-86"
    assert sample_entry._reader is None  # For this test setup


def test_init_invalid_type():
    with pytest.raises(Exception):
        ProxymanLogV2Entry("entry_name", "not a dict", reader=None)  # type: ignore


# --- Testing .id property ---
def test_id_property(sample_entry):
    assert sample_entry.id == "test-id-86"


def test_id_property_fallback():
    data_no_top_id = SAMPLE_ENTRY_DATA.copy()
    del data_no_top_id["id"]
    entry = ProxymanLogV2Entry(
        "request_0_filename-id-is-this", data_no_top_id, reader=None
    )
    assert entry.id == "filename-id-is-this"


# --- Testing .request properties ---
def test_request_url(sample_entry):
    assert isinstance(sample_entry.request.url, URL)
    assert (
        str(sample_entry.request.url)
        == "https://stream.broadpeak.io/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=SERVICEID"
    )
    assert sample_entry.request.url.host == "stream.broadpeak.io"
    assert (
        sample_entry.request.url.path_qs
        == "/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=SERVICEID"
    )


def test_request_headers(sample_entry):
    headers = sample_entry.request.headers
    assert isinstance(headers, dict)
    assert len(headers) == 3
    assert headers["Host"] == "stream.broadpeak.io"
    assert headers["User-Agent"] == "Mozilla/5.0 TestAgent"
    assert headers["Accept"] == "*/*"


def test_request_method(sample_entry):
    assert sample_entry.request.method == "GET"


def test_request_body_none(sample_entry):
    assert sample_entry.request.body is None


def test_request_body_present():
    req_body_b64 = base64.b64encode(b"hello request").decode("ascii")
    data = SAMPLE_ENTRY_DATA.copy()
    data["request"] = data["request"].copy()
    data["request"]["bodyData"] = req_body_b64
    entry = ProxymanLogV2Entry("req_body_entry", data, reader=None)
    assert entry.request.body == b"hello request"


# --- Testing .response properties ---
def test_response_status_code(sample_entry):
    assert sample_entry.response.status_code == 200


def test_response_headers(sample_entry):
    headers = sample_entry.response.headers
    assert isinstance(headers, dict)
    assert len(headers) == 3
    assert headers["Content-Type"] == "application/vnd.apple.mpegurl; charset=utf-8"
    assert headers["Date"] == "Mon, 28 Apr 2025 09:01:16 GMT"
    assert headers["Content-Length"] == "105"


def test_response_mime_type_and_content_type(sample_entry):
    assert (
        sample_entry.response.content_type
        == "application/vnd.apple.mpegurl; charset=utf-8"
    )
    assert sample_entry.response.mime_type == "application/vnd.apple.mpegurl"


# --- Testing .response.body properties ---
def test_response_body_text(sample_entry):
    body_text = sample_entry.response.body.text
    expected_text = "#EXTM3U\n#EXT-X-VERSION:4\n#EXTINF:4, no desc\nresource-1.ts\n#EXTINF:4, no desc\nresource-2.ts\n#EXT-X-ENDLIST"
    assert body_text == expected_text


def test_response_body_raw_size(sample_entry):
    # Based on the length of expected_text decoded from bodyData
    assert sample_entry.response.body.raw_size == 105


def test_response_body_compressed_size(sample_entry):
    # Using bodyEncodedSize from sample data
    assert sample_entry.response.body.compressed_size == 105


def test_response_body_text_no_body(no_body_entry):
    assert no_body_entry.response.body.text is None
    assert no_body_entry.response.body.raw_size == 0  # bodySize is 0 in fixture
    assert no_body_entry.response.body.compressed_size == 0  # bodyEncodedSize is 0


def test_response_body_text_invalid_base64(invalid_body_entry):
    # _get_decoded_body should return None if base64 is invalid
    assert invalid_body_entry.response.body._get_decoded_body() is None
    assert invalid_body_entry.response.body.text is None
    assert invalid_body_entry.response.body.raw_size == 0  # bodySize is 0 in fixture


def test_response_body_text_encoding_logic():
    # Test with a body that has a specific charset in header vs. one that doesn't
    # 1. Body with explicit latin-1 in header
    body_bytes_latin1 = b"H\xe9llo World"  # 'é' in latin-1
    body_b64_latin1 = base64.b64encode(body_bytes_latin1).decode("ascii")
    data_latin1 = SAMPLE_ENTRY_DATA.copy()
    data_latin1["response"] = data_latin1["response"].copy()
    data_latin1["response"]["bodyData"] = body_b64_latin1
    data_latin1["response"]["header"] = {
        "entries": [
            {"key": {"name": "Content-Type"}, "value": "text/plain; charset=latin-1"}
        ]
    }
    entry_latin1 = ProxymanLogV2Entry("latin1_entry", data_latin1, reader=None)
    assert entry_latin1.response.body.text == "H\xe9llo World"

    # 2. Body with no charset (should default to utf-8, fail if not utf-8 bytes)
    body_bytes_invalid_utf8 = (
        b"\xff\xfeHello"  # BOM for UTF-16, invalid for UTF-8 start
    )
    body_b64_invalid_utf8 = base64.b64encode(body_bytes_invalid_utf8).decode("ascii")
    data_invalid_utf8 = SAMPLE_ENTRY_DATA.copy()
    data_invalid_utf8["response"] = data_invalid_utf8["response"].copy()
    data_invalid_utf8["response"]["bodyData"] = body_b64_invalid_utf8
    data_invalid_utf8["response"]["header"] = {
        "entries": [{"key": {"name": "Content-Type"}, "value": "text/plain"}]
    }  # No charset
    entry_invalid_utf8 = ProxymanLogV2Entry(
        "invalid_utf8_entry", data_invalid_utf8, reader=None
    )
    # Should replace invalid sequences
    assert (
        "Hello" in entry_invalid_utf8.response.body.text
    )  # 정확한 치환 문자는 다를 수 있음

# --- Testing .content property ---
def test_content_property(sample_entry):
    assert sample_entry.content == sample_entry.response.body.text


# --- Testing .comment property ---
def test_comment_property(sample_entry):
    assert sample_entry.comment == "This is a sample entry comment."


def test_comment_property_missing():
    data_no_comment = SAMPLE_ENTRY_DATA.copy()
    del data_no_comment["notes"]
    entry = ProxymanLogV2Entry("no_comment_entry", data_no_comment, reader=None)
    assert entry.comment is None


# --- Testing .timings property (placeholder) ---
def test_timings_property(sample_entry):
    # Current _ProxymanTimingsDetails is a placeholder
    assert sample_entry.timeline is not None
    # Add more specific timing tests once _ProxymanTimingsDetails is implemented


# --- Testing utility methods and string representations ---
def test_get_raw_json(sample_entry):
    assert sample_entry.get_raw_json() == SAMPLE_ENTRY_DATA




def test_str_repr(sample_entry):
    expected_url = "https://stream.broadpeak.io/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=SERVICEID"
    assert (
        str(sample_entry) == f"ProxymanLogV2Entry(id=test-id-86 GET {expected_url} -> 200)"
    )
    assert (
        repr(sample_entry) == f"<ProxymanLogV2Entry id=test-id-86 GET {expected_url} -> 200>"
    )
