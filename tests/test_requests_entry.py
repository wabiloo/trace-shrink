"""Tests for RequestsResponseTraceEntry."""

import json
import os
import tempfile
from datetime import timedelta
from types import SimpleNamespace

import pytest
from yarl import URL

from trace_shrink import RequestsResponseTraceEntry, write_multifile_entry


def _fake_response(
    *,
    url: str = "https://example.com/path/to.m3u8",
    body: str = "#EXTM3U\n#EXT-X-VERSION:3\n",
    status_code: int = 200,
    headers: dict | None = None,
    elapsed_ms: int = 5,
    method: str = "GET",
    reason: str = "OK",
):
    """Create a minimal duck-typed object compatible with requests.Response."""
    req = SimpleNamespace(
        url=url,
        headers={"User-Agent": "pytest"},
        method=method,
        body=None,
    )
    body_bytes = body.encode("utf-8")
    elapsed_delta = timedelta(milliseconds=elapsed_ms)
    return SimpleNamespace(
        text=body,
        content=body_bytes,
        request=req,
        headers=headers or {"Content-Type": "application/x-mpegURL; charset=utf-8"},
        status_code=status_code,
        reason=reason,
        elapsed=elapsed_delta,
    )


def test_requests_response_trace_entry_basic():
    """Test basic creation and properties of RequestsResponseTraceEntry."""
    response = _fake_response()
    entry = RequestsResponseTraceEntry(response, index=1, entry_id="test-1")

    assert entry.index == 1
    assert entry.id == "test-1"
    assert entry.request.method == "GET"
    assert str(entry.request.url) == "https://example.com/path/to.m3u8"
    assert entry.response.status_code == 200
    assert entry.elapsed_ms == 5
    assert entry.reason == "OK"


def test_requests_response_trace_entry_url_parsing():
    """Test URL parsing from response."""
    response = _fake_response(url="https://example.com/test?foo=bar&baz=qux")
    entry = RequestsResponseTraceEntry(response)

    assert isinstance(entry.request.url, URL)
    assert entry.request.url.host == "example.com"
    assert entry.request.url.path == "/test"
    assert entry.request.url.query["foo"] == "bar"
    assert entry.request.url.query["baz"] == "qux"


def test_requests_response_trace_entry_headers():
    """Test header extraction from response."""
    response = _fake_response(
        headers={"Content-Type": "application/dash+xml", "X-Custom": "value"}
    )
    entry = RequestsResponseTraceEntry(response)

    assert entry.response.headers["Content-Type"] == "application/dash+xml"
    assert entry.response.headers["X-Custom"] == "value"
    assert entry.response.mime_type == "application/dash+xml"
    assert entry.response.content_type == "application/dash+xml"


def test_requests_response_trace_entry_body():
    """Test body extraction from response."""
    body_text = "#EXTM3U\n#EXT-X-VERSION:3\n"
    response = _fake_response(body=body_text)
    entry = RequestsResponseTraceEntry(response)

    assert entry.response.body.text == body_text
    assert entry.response.body.raw_size == len(body_text.encode("utf-8"))
    assert entry.response.body._get_decoded_body() == body_text.encode("utf-8")


def test_requests_response_trace_entry_timeline():
    """Test timeline creation from elapsed time."""
    response = _fake_response(elapsed_ms=100)
    entry = RequestsResponseTraceEntry(response)

    assert entry.timeline.response_end is not None
    assert entry.timeline.request_start is not None
    assert entry.timeline.response_end > entry.timeline.request_start

    # Check elapsed time matches
    delta = entry.timeline.response_end - entry.timeline.request_start
    assert abs(delta.total_seconds() * 1000 - 100) < 1  # Allow small timing differences


def test_requests_response_trace_entry_mutations():
    """Test that mutations work on RequestsResponseTraceEntry."""
    response = _fake_response()
    entry = RequestsResponseTraceEntry(response)

    # Test adding annotations
    entry.add_annotation("digest", "abc123")
    assert entry.annotations["digest"] == "abc123"

    # Test adding response headers
    entry.add_response_header("X-Custom", "test-value")
    assert entry.response.headers["X-Custom"] == "test-value"

    # Test adding request headers
    entry.add_request_header("X-Request-Id", "req-123")
    assert entry.request.headers["X-Request-Id"] == "req-123"

    # Test setting comment
    entry.set_comment("Test comment")
    assert entry.comment == "Test comment"

    # Test setting highlight
    entry.set_highlight("red")
    assert entry.highlight == "red"


def test_write_multifile_entry_basic():
    """Test basic writing of multifile entry."""
    response = _fake_response(body="test body content")
    entry = RequestsResponseTraceEntry(response, index=1)

    with tempfile.TemporaryDirectory() as td:
        write_multifile_entry(td, 1, entry)

        # Check meta.json exists
        meta_path = f"{td}/request_1.meta.json"
        assert os.path.exists(meta_path)

        # Check body file exists
        body_path = f"{td}/request_1.body"
        assert os.path.exists(body_path)

        # Verify meta.json content
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["request"]["url"] == "https://example.com/path/to.m3u8"
        assert meta["response"]["status_code"] == 200
        assert meta["elapsed_ms"] == 5

        # Verify body content
        with open(body_path, "rb") as f:
            assert f.read() == b"test body content"


def test_write_multifile_entry_with_annotations():
    """Test writing entry with annotations."""
    response = _fake_response()
    entry = RequestsResponseTraceEntry(response, index=1)
    entry.add_annotation("digest", "abc123")
    entry.add_annotation("custom", "custom-value")

    with tempfile.TemporaryDirectory() as td:
        write_multifile_entry(td, 1, entry)

        # Check annotation files exist
        assert os.path.exists(f"{td}/request_1.digest.txt")
        assert os.path.exists(f"{td}/request_1.custom.txt")

        # Verify annotation content
        with open(f"{td}/request_1.digest.txt") as f:
            assert f.read() == "abc123"

        with open(f"{td}/request_1.custom.txt") as f:
            assert f.read() == "custom-value"


def test_write_multifile_entry_with_body_extension():
    """Test writing entry with body extension."""
    response = _fake_response(body="<MPD></MPD>")
    entry = RequestsResponseTraceEntry(response, index=1)

    with tempfile.TemporaryDirectory() as td:
        write_multifile_entry(td, 1, entry, body_extension=".mpd")

        # Check body file has extension
        assert os.path.exists(f"{td}/request_1.body.mpd")
        assert not os.path.exists(f"{td}/request_1.body")


def test_write_multifile_entry_with_body_override():
    """Test writing entry with body bytes override."""
    response = _fake_response(body="original")
    entry = RequestsResponseTraceEntry(response, index=1)

    with tempfile.TemporaryDirectory() as td:
        write_multifile_entry(td, 1, entry, body_bytes=b"override content")

        # Verify override content was written
        with open(f"{td}/request_1.body", "rb") as f:
            assert f.read() == b"override content"


def test_write_multifile_entry_reason_phrase():
    """Test that reason phrase is included for RequestsResponseTraceEntry."""
    response = _fake_response(status_code=404, reason="Not Found")
    entry = RequestsResponseTraceEntry(response, index=1)

    with tempfile.TemporaryDirectory() as td:
        write_multifile_entry(td, 1, entry)

        with open(f"{td}/request_1.meta.json") as f:
            meta = json.load(f)

        assert meta["response"]["reason"] == "Not Found"
        assert meta["response"]["status_code"] == 404

