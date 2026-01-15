"""
Tests for archive modification capabilities (comments and headers).
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

from trace_shrink.entries import HarEntry
from trace_shrink.readers import HarReader
from trace_shrink.entries import ProxymanLogV2Entry
from trace_shrink.readers import ProxymanLogV2Reader


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

    def test_add_response_header_update_existing(self, har_entry):
        """Test updating an existing response header."""
        har_entry.add_response_header("Content-Type", "application/xml")
        
        headers = har_entry.response.headers
        assert headers["Content-Type"] == "application/xml"

    def test_add_request_header_new(self, har_entry):
        """Test adding a new request header."""
        initial_header_count = len(har_entry.request.headers)
        har_entry.add_request_header("X-Request-ID", "req-123")
        
        headers = har_entry.request.headers
        assert len(headers) == initial_header_count + 1
        assert headers["X-Request-ID"] == "req-123"

    def test_add_request_header_update_existing(self, har_entry):
        """Test updating an existing request header."""
        har_entry.add_request_header("Accept", "application/xml")
        
        headers = har_entry.request.headers
        assert headers["Accept"] == "application/xml"


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

    def test_add_response_header_update_existing(self, proxyman_entry):
        """Test updating an existing response header."""
        proxyman_entry.add_response_header("Content-Type", "application/xml")
        
        headers = proxyman_entry.response.headers
        assert headers["Content-Type"] == "application/xml"

    def test_add_request_header_new(self, proxyman_entry):
        """Test adding a new request header."""
        initial_header_count = len(proxyman_entry.request.headers)
        proxyman_entry.add_request_header("X-Request-ID", "req-123")
        
        headers = proxyman_entry.request.headers
        assert len(headers) == initial_header_count + 1
        assert headers["X-Request-ID"] == "req-123"

    def test_add_request_header_update_existing(self, proxyman_entry):
        """Test updating an existing request header."""
        proxyman_entry.add_request_header("Accept", "application/xml")
        
        headers = proxyman_entry.request.headers
        assert headers["Accept"] == "application/xml"


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
        """Test that set_highlight on HAR entries works."""
        har_entry.set_highlight("red")
        assert har_entry.highlight == "red"
        
        har_entry.set_highlight("strike")
        assert har_entry.highlight == "strike"
        
        # Invalid highlight should raise ValueError
        with pytest.raises(ValueError):
            har_entry.set_highlight("invalid")

    def test_proxyman_set_highlight_red(self, proxyman_entry):
        """Test setting red highlight on Proxyman entry."""
        proxyman_entry.set_highlight("red")
        assert proxyman_entry.highlight == "red"

    def test_proxyman_set_highlight_yellow(self, proxyman_entry):
        """Test setting yellow highlight on Proxyman entry."""
        proxyman_entry.set_highlight("yellow")
        assert proxyman_entry.highlight == "yellow"

    def test_proxyman_set_highlight_green(self, proxyman_entry):
        """Test setting green highlight on Proxyman entry."""
        proxyman_entry.set_highlight("green")
        assert proxyman_entry.highlight == "green"

    def test_proxyman_set_highlight_blue(self, proxyman_entry):
        """Test setting blue highlight on Proxyman entry."""
        proxyman_entry.set_highlight("blue")
        assert proxyman_entry.highlight == "blue"

    def test_proxyman_set_highlight_purple(self, proxyman_entry):
        """Test setting purple highlight on Proxyman entry."""
        proxyman_entry.set_highlight("purple")
        assert proxyman_entry.highlight == "purple"

    def test_proxyman_set_highlight_grey(self, proxyman_entry):
        """Test setting grey highlight on Proxyman entry."""
        proxyman_entry.set_highlight("grey")
        assert proxyman_entry.highlight == "grey"

    def test_proxyman_set_highlight_strike(self, proxyman_entry):
        """Test setting strike-through on Proxyman entry."""
        proxyman_entry.set_highlight("strike")
        assert proxyman_entry.highlight == "strike"

    def test_proxyman_set_highlight_invalid(self, proxyman_entry):
        """Test that invalid highlight values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid highlight value"):
            proxyman_entry.set_highlight("invalid")
        
        with pytest.raises(ValueError, match="Invalid highlight value"):
            proxyman_entry.set_highlight("")

    def test_proxyman_set_highlight_overwrite_color(self, proxyman_entry):
        """Test that setting a new color overwrites the old one."""
        proxyman_entry.set_highlight("red")
        assert proxyman_entry.highlight == "red"
        
        proxyman_entry.set_highlight("blue")
        assert proxyman_entry.highlight == "blue"

    def test_proxyman_set_highlight_color_after_strike(self, proxyman_entry):
        """Test that setting a color after strike works."""
        proxyman_entry.set_highlight("strike")
        assert proxyman_entry.highlight == "strike"
        
        proxyman_entry.set_highlight("green")
        assert proxyman_entry.highlight == "green"

    def test_proxyman_set_highlight_strike_after_color(self, proxyman_entry):
        """Test that setting strike after color works."""
        proxyman_entry.set_highlight("blue")
        assert proxyman_entry.highlight == "blue"
        
        proxyman_entry.set_highlight("strike")
        assert proxyman_entry.highlight == "strike"

