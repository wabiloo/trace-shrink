"""
Tests for archive modification capabilities (comments and headers).
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

from trace_shrink import HarEntry, HarReader, ProxymanLogV2Entry, ProxymanLogV2Reader


# Sample HAR entry data for testing
SAMPLE_HAR_ENTRY_DICT = {
    "startedDateTime": "2024-05-15T12:00:00.123Z",
    "time": 150.5,
    "request": {
        "method": "GET",
        "url": "https://api.example.com/v1/data",
        "httpVersion": "HTTP/1.1",
        "headers": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Accept", "value": "application/json"},
        ],
    },
    "response": {
        "status": 200,
        "statusText": "OK",
        "httpVersion": "HTTP/1.1",
        "headers": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Content-Length", "value": "100"},
        ],
        "content": {
            "size": 100,
            "mimeType": "application/json",
            "text": '{"key": "value"}',
        },
        "bodySize": 100,
    },
    "cache": {},
    "timings": {
        "blocked": 10.1,
        "dns": -1,
        "connect": 25.5,
        "send": 20.2,
        "wait": 50.3,
        "receive": 44.4,
    },
}


# Sample Proxyman entry data for testing
SAMPLE_PROXYMAN_ENTRY_DICT = {
    "request": {
        "host": "api.example.com",
        "uri": "/v1/data",
        "scheme": "https",
        "port": 443,
        "header": {
            "entries": [
                {"key": {"name": "Content-Type"}, "value": "application/json"},
                {"key": {"name": "Accept"}, "value": "application/json"},
            ]
        },
        "method": {"name": "GET"},
        "fullPath": "https://api.example.com/v1/data",
        "bodyData": None,
    },
    "response": {
        "status": {"code": 200, "phrase": "OK"},
        "header": {
            "entries": [
                {"key": {"name": "Content-Type"}, "value": "application/json"},
                {"key": {"name": "Content-Length"}, "value": "100"},
            ]
        },
        "bodyData": None,
        "bodySize": 0,
        "bodyEncodedSize": 0,
    },
    "id": "test-entry-123",
}


class TestHarEntryModification:
    """Tests for modifying HAR entries."""

    @pytest.fixture
    def har_entry(self):
        """Create a HarEntry instance for testing."""
        return HarEntry(SAMPLE_HAR_ENTRY_DICT.copy(), reader=None, entry_index=0)

    def test_set_comment(self, har_entry):
        """Test setting a comment on a HAR entry."""
        assert har_entry.comment is None
        har_entry.set_comment("This is a test comment")
        assert har_entry.comment == "This is a test comment"
        assert har_entry._raw_data["comment"] == "This is a test comment"

    def test_set_comment_overwrite(self, har_entry):
        """Test overwriting an existing comment."""
        har_entry.set_comment("First comment")
        assert har_entry.comment == "First comment"
        har_entry.set_comment("Second comment")
        assert har_entry.comment == "Second comment"

    def test_add_response_header_new(self, har_entry):
        """Test adding a new response header."""
        initial_header_count = len(har_entry.response.headers)
        har_entry.add_response_header("X-Custom-Header", "custom-value")
        
        headers = har_entry.response.headers
        assert len(headers) == initial_header_count + 1
        assert headers["X-Custom-Header"] == "custom-value"
        
        # Verify it's in raw data
        response_headers = har_entry._raw_data["response"]["headers"]
        assert any(h["name"] == "X-Custom-Header" and h["value"] == "custom-value" for h in response_headers)

    def test_add_response_header_update_existing(self, har_entry):
        """Test updating an existing response header."""
        har_entry.add_response_header("Content-Type", "application/xml")
        
        headers = har_entry.response.headers
        assert headers["Content-Type"] == "application/xml"
        
        # Verify only one Content-Type header exists
        response_headers = har_entry._raw_data["response"]["headers"]
        content_type_headers = [h for h in response_headers if h["name"] == "Content-Type"]
        assert len(content_type_headers) == 1
        assert content_type_headers[0]["value"] == "application/xml"

    def test_add_request_header_new(self, har_entry):
        """Test adding a new request header."""
        initial_header_count = len(har_entry.request.headers)
        har_entry.add_request_header("X-Request-ID", "req-123")
        
        headers = har_entry.request.headers
        assert len(headers) == initial_header_count + 1
        assert headers["X-Request-ID"] == "req-123"
        
        # Verify it's in raw data
        request_headers = har_entry._raw_data["request"]["headers"]
        assert any(h["name"] == "X-Request-ID" and h["value"] == "req-123" for h in request_headers)

    def test_add_request_header_update_existing(self, har_entry):
        """Test updating an existing request header."""
        har_entry.add_request_header("Accept", "application/xml")
        
        headers = har_entry.request.headers
        assert headers["Accept"] == "application/xml"
        
        # Verify only one Accept header exists
        request_headers = har_entry._raw_data["request"]["headers"]
        accept_headers = [h for h in request_headers if h["name"] == "Accept"]
        assert len(accept_headers) == 1
        assert accept_headers[0]["value"] == "application/xml"


class TestProxymanEntryModification:
    """Tests for modifying Proxyman entries."""

    @pytest.fixture
    def proxyman_entry(self):
        """Create a ProxymanLogV2Entry instance for testing."""
        return ProxymanLogV2Entry(
            "request_0_test-entry-123", SAMPLE_PROXYMAN_ENTRY_DICT.copy(), reader=None
        )

    def test_set_comment(self, proxyman_entry):
        """Test setting a comment/note on a Proxyman entry."""
        assert proxyman_entry.comment is None
        proxyman_entry.set_comment("This is a test note")
        assert proxyman_entry.comment == "This is a test note"
        assert proxyman_entry._raw_data["style"]["comment"] == "This is a test note"

    def test_set_comment_overwrite(self, proxyman_entry):
        """Test overwriting an existing comment."""
        proxyman_entry.set_comment("First note")
        assert proxyman_entry.comment == "First note"
        proxyman_entry.set_comment("Second note")
        assert proxyman_entry.comment == "Second note"

    def test_add_response_header_new(self, proxyman_entry):
        """Test adding a new response header."""
        initial_header_count = len(proxyman_entry.response.headers)
        proxyman_entry.add_response_header("X-Custom-Header", "custom-value")
        
        headers = proxyman_entry.response.headers
        assert len(headers) == initial_header_count + 1
        assert headers["X-Custom-Header"] == "custom-value"
        
        # Verify it's in raw data
        response_header_entries = proxyman_entry._raw_data["response"]["header"]["entries"]
        assert any(
            e.get("key", {}).get("name") == "X-Custom-Header" and e.get("value") == "custom-value"
            for e in response_header_entries
        )

    def test_add_response_header_update_existing(self, proxyman_entry):
        """Test updating an existing response header."""
        proxyman_entry.add_response_header("Content-Type", "application/xml")
        
        headers = proxyman_entry.response.headers
        assert headers["Content-Type"] == "application/xml"
        
        # Verify only one Content-Type header exists
        response_header_entries = proxyman_entry._raw_data["response"]["header"]["entries"]
        content_type_headers = [
            e for e in response_header_entries
            if e.get("key", {}).get("name") == "Content-Type"
        ]
        assert len(content_type_headers) == 1
        assert content_type_headers[0]["value"] == "application/xml"

    def test_add_request_header_new(self, proxyman_entry):
        """Test adding a new request header."""
        initial_header_count = len(proxyman_entry.request.headers)
        proxyman_entry.add_request_header("X-Request-ID", "req-123")
        
        headers = proxyman_entry.request.headers
        assert len(headers) == initial_header_count + 1
        assert headers["X-Request-ID"] == "req-123"
        
        # Verify it's in raw data
        request_header_entries = proxyman_entry._raw_data["request"]["header"]["entries"]
        assert any(
            e.get("key", {}).get("name") == "X-Request-ID" and e.get("value") == "req-123"
            for e in request_header_entries
        )

    def test_add_request_header_update_existing(self, proxyman_entry):
        """Test updating an existing request header."""
        proxyman_entry.add_request_header("Accept", "application/xml")
        
        headers = proxyman_entry.request.headers
        assert headers["Accept"] == "application/xml"
        
        # Verify only one Accept header exists
        request_header_entries = proxyman_entry._raw_data["request"]["header"]["entries"]
        accept_headers = [
            e for e in request_header_entries
            if e.get("key", {}).get("name") == "Accept"
        ]
        assert len(accept_headers) == 1
        assert accept_headers[0]["value"] == "application/xml"


class TestHarReaderSave:
    """Tests for saving modified HAR files."""

    @pytest.fixture
    def sample_har_file(self, tmp_path):
        """Create a temporary HAR file for testing."""
        har_data = {
            "log": {
                "version": "1.2",
                "creator": {"name": "test", "version": "1.0"},
                "entries": [SAMPLE_HAR_ENTRY_DICT.copy()],
            }
        }
        har_path = tmp_path / "test.har"
        with open(har_path, "w", encoding="utf-8") as f:
            json.dump(har_data, f)
        return str(har_path)

    def test_save_har_with_modifications(self, sample_har_file, tmp_path):
        """Test saving a HAR file after making modifications."""
        reader = HarReader(sample_har_file)
        entry = reader.entries[0]
        
        # Make modifications
        entry.set_comment("Modified comment")
        entry.add_response_header("X-Test-Header", "test-value")
        
        # Save to a new file
        output_path = str(tmp_path / "modified.har")
        reader.save(output_path)
        
        # Verify the saved file
        assert os.path.exists(output_path)
        
        # Reload and verify modifications
        reader2 = HarReader(output_path)
        entry2 = reader2.entries[0]
        assert entry2.comment == "Modified comment"
        assert entry2.response.headers["X-Test-Header"] == "test-value"

    def test_save_har_overwrite_original(self, sample_har_file):
        """Test saving a HAR file to the original path."""
        reader = HarReader(sample_har_file)
        entry = reader.entries[0]
        
        # Make modifications
        entry.set_comment("Overwritten comment")
        
        # Save to original path
        reader.save()
        
        # Reload and verify modifications
        reader2 = HarReader(sample_har_file)
        entry2 = reader2.entries[0]
        assert entry2.comment == "Overwritten comment"

    def test_save_har_multiple_entries(self, tmp_path):
        """Test saving a HAR file with multiple entries."""
        har_data = {
            "log": {
                "version": "1.2",
                "creator": {"name": "test", "version": "1.0"},
                "entries": [
                    SAMPLE_HAR_ENTRY_DICT.copy(),
                    {**SAMPLE_HAR_ENTRY_DICT.copy(), "request": {**SAMPLE_HAR_ENTRY_DICT["request"].copy(), "url": "https://example.com/other"}},
                ],
            }
        }
        har_path = tmp_path / "multi.har"
        with open(har_path, "w", encoding="utf-8") as f:
            json.dump(har_data, f)
        
        reader = HarReader(str(har_path))
        
        # Modify both entries
        reader.entries[0].set_comment("First entry")
        reader.entries[1].set_comment("Second entry")
        
        output_path = str(tmp_path / "multi_modified.har")
        reader.save(output_path)
        
        # Verify both modifications persisted
        reader2 = HarReader(output_path)
        assert reader2.entries[0].comment == "First entry"
        assert reader2.entries[1].comment == "Second entry"


class TestProxymanReaderSave:
    """Tests for saving modified Proxyman log files."""

    @pytest.fixture
    def sample_proxyman_file(self, tmp_path):
        """Create a temporary Proxyman log file for testing."""
        import zipfile
        
        proxyman_path = tmp_path / "test.proxymanlogv2"
        
        # Create a ZIP archive with a sample entry
        with zipfile.ZipFile(proxyman_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "request_0_test-entry-123",
                json.dumps(SAMPLE_PROXYMAN_ENTRY_DICT.copy(), indent=2),
            )
        
        return str(proxyman_path)

    def test_save_proxyman_with_modifications(self, sample_proxyman_file, tmp_path):
        """Test saving a Proxyman log file after making modifications."""
        reader = ProxymanLogV2Reader(sample_proxyman_file)
        entry = reader.entries[0]
        
        # Make modifications
        entry.set_comment("Modified note")
        entry.add_response_header("X-Test-Header", "test-value")
        
        # Save to a new file
        output_path = str(tmp_path / "modified.proxymanlogv2")
        reader.save(output_path)
        
        # Verify the saved file
        assert os.path.exists(output_path)
        
        # Reload and verify modifications
        reader2 = ProxymanLogV2Reader(output_path)
        entry2 = reader2.entries[0]
        assert entry2.comment == "Modified note"
        assert entry2.response.headers["X-Test-Header"] == "test-value"

    def test_save_proxyman_overwrite_original(self, sample_proxyman_file):
        """Test saving a Proxyman log file to the original path."""
        reader = ProxymanLogV2Reader(sample_proxyman_file)
        entry = reader.entries[0]
        
        # Make modifications
        entry.set_comment("Overwritten note")
        
        # Save to original path
        reader.save()
        
        # Reload and verify modifications
        reader2 = ProxymanLogV2Reader(sample_proxyman_file)
        entry2 = reader2.entries[0]
        assert entry2.comment == "Overwritten note"

    def test_save_proxyman_multiple_entries(self, tmp_path):
        """Test saving a Proxyman log file with multiple entries."""
        import zipfile
        
        proxyman_path = tmp_path / "multi.proxymanlogv2"
        
        # Create a ZIP archive with multiple entries
        entry2_data = {
            **SAMPLE_PROXYMAN_ENTRY_DICT.copy(),
            "id": "test-entry-456",
            "request": {
                **SAMPLE_PROXYMAN_ENTRY_DICT["request"].copy(),
                "uri": "/v1/other",
            },
        }
        
        with zipfile.ZipFile(proxyman_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "request_0_test-entry-123",
                json.dumps(SAMPLE_PROXYMAN_ENTRY_DICT.copy(), indent=2),
            )
            zf.writestr(
                "request_1_test-entry-456",
                json.dumps(entry2_data, indent=2),
            )
        
        reader = ProxymanLogV2Reader(str(proxyman_path))
        
        # Modify both entries
        reader.entries[0].set_comment("First entry")
        reader.entries[1].set_comment("Second entry")
        
        output_path = str(tmp_path / "multi_modified.proxymanlogv2")
        reader.save(output_path)
        
        # Verify both modifications persisted
        reader2 = ProxymanLogV2Reader(output_path)
        assert reader2.entries[0].comment == "First entry"
        assert reader2.entries[1].comment == "Second entry"


class TestModificationIntegration:
    """Integration tests for modifying and saving archives."""

    def test_har_modify_and_save_roundtrip(self, tmp_path):
        """Test modifying a HAR entry and saving it, then reloading."""
        har_data = {
            "log": {
                "version": "1.2",
                "creator": {"name": "test", "version": "1.0"},
                "entries": [SAMPLE_HAR_ENTRY_DICT.copy()],
            }
        }
        har_path = tmp_path / "roundtrip.har"
        with open(har_path, "w", encoding="utf-8") as f:
            json.dump(har_data, f)
        
        # Load, modify, save
        reader1 = HarReader(str(har_path))
        entry1 = reader1.entries[0]
        entry1.set_comment("Roundtrip test")
        entry1.add_response_header("X-Roundtrip", "yes")
        entry1.add_request_header("X-Request-Modified", "true")
        
        output_path = str(tmp_path / "roundtrip_modified.har")
        reader1.save(output_path)
        
        # Reload and verify
        reader2 = HarReader(output_path)
        entry2 = reader2.entries[0]
        assert entry2.comment == "Roundtrip test"
        assert entry2.response.headers["X-Roundtrip"] == "yes"
        assert entry2.request.headers["X-Request-Modified"] == "true"

    def test_proxyman_modify_and_save_roundtrip(self, tmp_path):
        """Test modifying a Proxyman entry and saving it, then reloading."""
        import zipfile
        
        proxyman_path = tmp_path / "roundtrip.proxymanlogv2"
        
        with zipfile.ZipFile(proxyman_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "request_0_test-entry-123",
                json.dumps(SAMPLE_PROXYMAN_ENTRY_DICT.copy(), indent=2),
            )
        
        # Load, modify, save
        reader1 = ProxymanLogV2Reader(str(proxyman_path))
        entry1 = reader1.entries[0]
        entry1.set_comment("Roundtrip test")
        entry1.add_response_header("X-Roundtrip", "yes")
        entry1.add_request_header("X-Request-Modified", "true")
        
        output_path = str(tmp_path / "roundtrip_modified.proxymanlogv2")
        reader1.save(output_path)
        
        # Reload and verify
        reader2 = ProxymanLogV2Reader(output_path)
        entry2 = reader2.entries[0]
        assert entry2.comment == "Roundtrip test"
        assert entry2.response.headers["X-Roundtrip"] == "yes"
        assert entry2.request.headers["X-Request-Modified"] == "true"


class TestHighlightModification:
    """Tests for highlighting entries."""

    @pytest.fixture
    def har_entry(self):
        """Create a HarEntry instance for testing."""
        return HarEntry(SAMPLE_HAR_ENTRY_DICT.copy(), reader=None, entry_index=0)

    @pytest.fixture
    def proxyman_entry(self):
        """Create a ProxymanLogV2Entry instance for testing."""
        return ProxymanLogV2Entry(
            "request_0_test-entry-123", SAMPLE_PROXYMAN_ENTRY_DICT.copy(), reader=None
        )

    def test_har_set_highlight(self, har_entry):
        """Test that set_highlight on HAR entries stores highlight in _highlight field."""
        assert "_highlight" not in har_entry._raw_data
        
        har_entry.set_highlight("red")
        assert har_entry._raw_data["_highlight"] == "red"
        
        har_entry.set_highlight("strike")
        assert har_entry._raw_data["_highlight"] == "strike"
        
        # Invalid highlight should raise ValueError
        with pytest.raises(ValueError):
            har_entry.set_highlight("invalid")

    def test_proxyman_set_highlight_red(self, proxyman_entry):
        """Test setting red highlight on Proxyman entry."""
        proxyman_entry.set_highlight("red")
        assert proxyman_entry._raw_data["style"]["color"] == 0
        assert "textStyle" not in proxyman_entry._raw_data.get("style", {})

    def test_proxyman_set_highlight_yellow(self, proxyman_entry):
        """Test setting yellow highlight on Proxyman entry."""
        proxyman_entry.set_highlight("yellow")
        assert proxyman_entry._raw_data["style"]["color"] == 1

    def test_proxyman_set_highlight_green(self, proxyman_entry):
        """Test setting green highlight on Proxyman entry."""
        proxyman_entry.set_highlight("green")
        assert proxyman_entry._raw_data["style"]["color"] == 2

    def test_proxyman_set_highlight_blue(self, proxyman_entry):
        """Test setting blue highlight on Proxyman entry."""
        proxyman_entry.set_highlight("blue")
        assert proxyman_entry._raw_data["style"]["color"] == 3

    def test_proxyman_set_highlight_purple(self, proxyman_entry):
        """Test setting purple highlight on Proxyman entry."""
        proxyman_entry.set_highlight("purple")
        assert proxyman_entry._raw_data["style"]["color"] == 4

    def test_proxyman_set_highlight_grey(self, proxyman_entry):
        """Test setting grey highlight on Proxyman entry."""
        proxyman_entry.set_highlight("grey")
        assert proxyman_entry._raw_data["style"]["color"] == 5

    def test_proxyman_set_highlight_strike(self, proxyman_entry):
        """Test setting strike-through on Proxyman entry."""
        proxyman_entry.set_highlight("strike")
        assert proxyman_entry._raw_data["style"]["textStyle"] == 0
        assert "color" not in proxyman_entry._raw_data.get("style", {})

    def test_proxyman_set_highlight_invalid(self, proxyman_entry):
        """Test that invalid highlight values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid highlight value"):
            proxyman_entry.set_highlight("invalid")
        
        with pytest.raises(ValueError, match="Invalid highlight value"):
            proxyman_entry.set_highlight("")

    def test_proxyman_set_highlight_overwrite_color(self, proxyman_entry):
        """Test that setting a new color overwrites the old one."""
        proxyman_entry.set_highlight("red")
        assert proxyman_entry._raw_data["style"]["color"] == 0
        
        proxyman_entry.set_highlight("blue")
        assert proxyman_entry._raw_data["style"]["color"] == 3
        assert "textStyle" not in proxyman_entry._raw_data.get("style", {})

    def test_proxyman_set_highlight_color_after_strike(self, proxyman_entry):
        """Test that setting a color after strike removes textStyle."""
        proxyman_entry.set_highlight("strike")
        assert proxyman_entry._raw_data["style"]["textStyle"] == 0
        
        proxyman_entry.set_highlight("green")
        assert proxyman_entry._raw_data["style"]["color"] == 2
        assert "textStyle" not in proxyman_entry._raw_data.get("style", {})

    def test_proxyman_set_highlight_strike_after_color(self, proxyman_entry):
        """Test that setting strike after color removes color."""
        proxyman_entry.set_highlight("blue")
        assert proxyman_entry._raw_data["style"]["color"] == 3
        
        proxyman_entry.set_highlight("strike")
        assert proxyman_entry._raw_data["style"]["textStyle"] == 0
        assert "color" not in proxyman_entry._raw_data.get("style", {})

    def test_proxyman_set_highlight_preserves_existing_style_fields(self, proxyman_entry):
        """Test that set_highlight preserves other style fields like comment."""
        # Set up existing style with comment
        proxyman_entry._raw_data["style"] = {"comment": "Existing comment"}
        
        proxyman_entry.set_highlight("red")
        assert proxyman_entry._raw_data["style"]["color"] == 0
        assert proxyman_entry._raw_data["style"]["comment"] == "Existing comment"

    def test_proxyman_set_highlight_save_and_reload(self, tmp_path):
        """Test that highlight persists after save and reload."""
        import zipfile
        
        proxyman_path = tmp_path / "highlight_test.proxymanlogv2"
        
        with zipfile.ZipFile(proxyman_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "request_0_test-entry-123",
                json.dumps(SAMPLE_PROXYMAN_ENTRY_DICT.copy(), indent=2),
            )
        
        # Load, set highlight, save
        reader1 = ProxymanLogV2Reader(str(proxyman_path))
        entry1 = reader1.entries[0]
        entry1.set_highlight("blue")
        
        output_path = str(tmp_path / "highlight_modified.proxymanlogv2")
        reader1.save(output_path)
        
        # Reload and verify
        reader2 = ProxymanLogV2Reader(output_path)
        entry2 = reader2.entries[0]
        assert entry2._raw_data["style"]["color"] == 3

