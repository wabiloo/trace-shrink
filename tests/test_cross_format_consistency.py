import json
from pathlib import Path

import pytest
from yarl import URL

from trace_shrink import HarEntry, ProxymanLogV2Entry

# Define paths to the archive files
ARCHIVES_DIR = Path(__file__).parent / "archives"
CHROME_HAR_FILE = ARCHIVES_DIR / "har_entry_chrome.json"
PROXYMAN_HAR_FILE = ARCHIVES_DIR / "har_entry_proxyman.json"
PROXYMAN_LOG_FILE = ARCHIVES_DIR / "proxyman_entry.json"


@pytest.fixture(scope="module")
def chrome_har_data():
    with open(CHROME_HAR_FILE, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def proxyman_har_data():
    with open(PROXYMAN_HAR_FILE, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def proxyman_log_data():
    with open(PROXYMAN_LOG_FILE, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def chrome_har_entry(chrome_har_data):
    # HAR files usually contain a list of entries under log.entries
    # For this specific file, it is a single entry object, extracted from the list
    return HarEntry(chrome_har_data, reader=None, entry_index=1)


@pytest.fixture(scope="module")
def proxyman_har_entry(proxyman_har_data):
    # Similar to Chrome, assuming the JSON is the entry itself, not a full log
    # The JSON is a list of entries, but we only want the first one
    return HarEntry(proxyman_har_data, reader=None, entry_index=1)


@pytest.fixture(scope="module")
def proxyman_log_entry(proxyman_log_data):
    # ProxymanLogV2Entry takes filename_id, raw_data, reader
    # The filename_id can be arbitrary for this test as long as it's a string
    return ProxymanLogV2Entry(
        raw_data=proxyman_log_data,
        entry_name=f"request_0_{proxyman_log_data.get('id', 'proxyman_entry')}",
        reader=None,
    )


def test_files_exist():
    """Ensure the test files are present."""
    assert CHROME_HAR_FILE.exists(), f"{CHROME_HAR_FILE} not found."
    assert PROXYMAN_HAR_FILE.exists(), f"{PROXYMAN_HAR_FILE} not found."
    assert PROXYMAN_LOG_FILE.exists(), f"{PROXYMAN_LOG_FILE} not found."


class TestCrossFormatConsistency:
    def test_request_url(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare the request URL across all three entry types."""
        chrome_url = chrome_har_entry.request.url
        proxyman_har_url = proxyman_har_entry.request.url
        proxyman_log_url = proxyman_log_entry.request.url

        # Compare string representations for equality
        # yarl.URL objects might differ in internal structure but represent the same URL
        assert str(chrome_url) == str(proxyman_har_url)
        assert str(chrome_url) == str(proxyman_log_url)

    def test_request_method(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare the request method."""
        assert chrome_har_entry.request.method == proxyman_har_entry.request.method
        assert chrome_har_entry.request.method == proxyman_log_entry.request.method

    def test_response_status_code(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare the response status code."""
        assert (
            chrome_har_entry.response.status_code
            == proxyman_har_entry.response.status_code
        )
        assert (
            chrome_har_entry.response.status_code
            == proxyman_log_entry.response.status_code
        )

    # Helper for header comparison
    def _normalize_headers(self, headers: dict) -> dict:
        return {k.lower(): v for k, v in headers.items()}

    def test_request_headers_common(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare common request headers, ignoring case of keys."""
        chrome_headers = self._normalize_headers(chrome_har_entry.request.headers)
        proxyman_har_headers = self._normalize_headers(
            proxyman_har_entry.request.headers
        )
        proxyman_log_headers = self._normalize_headers(
            proxyman_log_entry.request.headers
        )

        # Identify common header keys (all lowercase)
        common_keys = (
            set(chrome_headers.keys())
            & set(proxyman_har_headers.keys())
            & set(proxyman_log_headers.keys())
        )

        # Assert that some common keys are found (sanity check)
        # Based on the provided proxyman_entry.json, these should be common.
        # We might need to adjust this if the other files have radically different minimal headers.
        expected_common_keys = {
            "host",
            "user-agent",
            "accept",
            "origin",
            "referer",
        }  # Example, adjust as needed
        assert expected_common_keys.issubset(common_keys), (
            f"Expected common request headers missing. Found: {common_keys}"
        )

        for key in common_keys:
            # Handle potential slight differences in complex headers like User-Agent if necessary
            # For now, direct comparison
            assert chrome_headers[key] == proxyman_har_headers[key], (
                f"Request header '{key}' mismatch (chrome vs proxyman HAR)"
            )
            assert chrome_headers[key] == proxyman_log_headers[key], (
                f"Request header '{key}' mismatch (chrome vs proxyman Log)"
            )

    def test_response_headers_common(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare common response headers, ignoring case of keys."""
        chrome_headers = self._normalize_headers(chrome_har_entry.response.headers)
        proxyman_har_headers = self._normalize_headers(
            proxyman_har_entry.response.headers
        )
        proxyman_log_headers = self._normalize_headers(
            proxyman_log_entry.response.headers
        )

        common_keys = (
            set(chrome_headers.keys())
            & set(proxyman_har_headers.keys())
            & set(proxyman_log_headers.keys())
        )

        # Based on the provided proxyman_entry.json, these should be common.
        expected_common_keys = {
            "content-type",
            "connection",
            "date",
            "cache-control",
            "vary",
        }  # Example, adjust as needed
        assert expected_common_keys.issubset(common_keys), (
            f"Expected common response headers missing. Found: {common_keys}"
        )

        for key in common_keys:
            # Special handling for 'Date' header as it will always be different for live requests.
            # The example files are static, so Date *should* be the same if they represent the *exact* same tx.
            # If they were captured at different times, this would fail. For now, assume static and identical capture.
            # Similar for 'Content-Length' if encoding/compression differences exist.
            # For now, direct comparison for most.
            assert chrome_headers[key] == proxyman_har_headers[key], (
                f"Response header '{key}' mismatch (chrome vs proxyman HAR)"
            )
            assert chrome_headers[key] == proxyman_log_headers[key], (
                f"Response header '{key}' mismatch (chrome vs proxyman Log)"
            )

    def test_response_body_text_consistency(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare the decoded response body text."""
        chrome_res_text = chrome_har_entry.response.body.text
        proxyman_har_res_text = proxyman_har_entry.response.body.text
        proxyman_log_res_text = proxyman_log_entry.response.body.text

        # Basic assertions for non-null before comparison
        assert chrome_res_text is not None, "Chrome HAR response text is None"
        assert proxyman_har_res_text is not None, "Proxyman HAR response text is None"
        assert proxyman_log_res_text is not None, "Proxyman Log response text is None"

        # Clean whitespace differences, especially trailing newlines, which can vary.
        assert chrome_res_text.strip() == proxyman_har_res_text.strip()
        assert chrome_res_text.strip() == proxyman_log_res_text.strip()

    def test_response_content_type(
        self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry
    ):
        """Compare the response Content-Type (MIME type part)."""
        # response.mime_type should give just the MIME type without charset etc.
        chrome_mime = chrome_har_entry.response.mime_type
        proxyman_har_mime = proxyman_har_entry.response.mime_type
        proxyman_log_mime = proxyman_log_entry.response.mime_type

        assert chrome_mime == proxyman_har_mime
        assert chrome_mime == proxyman_log_mime
        # Based on the proxyman_entry, it's an HLS manifest
        assert chrome_mime == "application/vnd.apple.mpegurl"


class TestCrossFormatDifferences:
    def test_entry_id(self, chrome_har_entry, proxyman_har_entry, proxyman_log_entry):
        """Test the ID of the Proxyman Log entry."""
        assert chrome_har_entry.id == "index-1"
        assert proxyman_har_entry.id == "15069"
        assert proxyman_log_entry.id == "15069"
