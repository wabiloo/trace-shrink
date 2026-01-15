"""Tests for RequestsResponseTraceEntry."""

import json
import os
import tempfile
from datetime import timedelta
from types import SimpleNamespace

from yarl import URL

from trace_shrink import Format
from trace_shrink.entries import RequestsResponseTraceEntry
from trace_shrink.writers import MultiFileWriter


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


def test_multifile_writer_class():
    """Test MultiFileWriter class."""
    response = _fake_response(body="test content")
    entry = RequestsResponseTraceEntry(response, index=1)
    entry.add_annotation("digest", "test-digest")

    with tempfile.TemporaryDirectory() as td:
        writer = MultiFileWriter(td)
        writer.add_entry(entry, index=42)

        # Check files exist with zero-padded index
        assert os.path.exists(f"{td}/request_000042.meta.json")
        assert os.path.exists(f"{td}/request_000042.body.m3u8")
        assert os.path.exists(f"{td}/request_000042.digest.txt")

        # Verify content
        with open(f"{td}/request_000042.meta.json") as f:
            meta = json.load(f)
            assert meta["response"]["status_code"] == 200

        with open(f"{td}/request_000042.body.m3u8", "rb") as f:
            assert f.read() == b"test content"

        with open(f"{td}/request_000042.digest.txt") as f:
            assert f.read() == "test-digest"


def test_multifile_writer_extension_from_url():
    """Test that extension is determined from URL when content-type is missing."""
    # Create response without Content-Type header
    req = SimpleNamespace(
        url="https://example.com/manifest.mpd",
        headers={"User-Agent": "pytest"},
        method="GET",
        body=None,
    )
    body_bytes = b"<MPD></MPD>"
    response = SimpleNamespace(
        text="<MPD></MPD>",
        content=body_bytes,
        request=req,
        headers={},  # Explicitly no Content-Type
        status_code=200,
        reason="OK",
        elapsed=timedelta(milliseconds=5),
    )
    entry = RequestsResponseTraceEntry(response, index=1)

    with tempfile.TemporaryDirectory() as td:
        writer = MultiFileWriter(td)
        writer.add_entry(entry, index=1)

        # Extension should come from URL (.mpd)
        assert os.path.exists(f"{td}/request_000001.body.mpd")
        assert not os.path.exists(f"{td}/request_000001.body")


def test_multifile_writer_extension_prefers_content_type():
    """Test that content-type takes precedence over URL extension."""
    response = _fake_response(
        url="https://example.com/manifest.mpd",  # URL suggests .mpd
        body="#EXTM3U",
        headers={"Content-Type": "application/x-mpegURL"},  # But content-type is HLS
    )
    entry = RequestsResponseTraceEntry(response, index=1)

    with tempfile.TemporaryDirectory() as td:
        writer = MultiFileWriter(td)
        writer.add_entry(entry, index=1)

        # Extension should come from content-type (.m3u8), not URL (.mpd)
        assert os.path.exists(f"{td}/request_000001.body.m3u8")
        assert not os.path.exists(f"{td}/request_000001.body.mpd")


def test_trace_entry_format_property():
    """Test the format property on TraceEntry."""
    # Test HLS format from content-type
    response = _fake_response(
        url="https://example.com/manifest.m3u8",
        headers={"Content-Type": "application/x-mpegURL"},
    )
    entry = RequestsResponseTraceEntry(response)
    assert entry.format == Format.HLS

    # Test DASH format from content-type
    response = _fake_response(
        url="https://example.com/manifest.mpd",
        headers={"Content-Type": "application/dash+xml"},
    )
    entry = RequestsResponseTraceEntry(response)
    assert entry.format == Format.DASH

    # Test format detection from URL when content-type is missing
    req = SimpleNamespace(
        url="https://example.com/manifest.m3u8",
        headers={"User-Agent": "pytest"},
        method="GET",
        body=None,
    )
    body_bytes = b"#EXTM3U"
    response = SimpleNamespace(
        text="#EXTM3U",
        content=body_bytes,
        request=req,
        headers={},  # No Content-Type
        status_code=200,
        reason="OK",
        elapsed=timedelta(milliseconds=5),
    )
    entry = RequestsResponseTraceEntry(response)
    assert entry.format == Format.HLS

    # Test None format for non-ABR content
    response = _fake_response(
        url="https://example.com/data.json",
        headers={"Content-Type": "application/json"},
    )
    entry = RequestsResponseTraceEntry(response)
    assert entry.format is None


def test_trace_entry_content_bytes_property():
    """Test the content_bytes property on TraceEntry."""
    # Test with text content (HLS)
    body_text = "#EXTM3U\n#EXT-X-VERSION:3\n"
    response = _fake_response(body=body_text)
    entry = RequestsResponseTraceEntry(response)
    
    # content_bytes should always return bytes
    content_bytes = entry.content_bytes
    assert isinstance(content_bytes, bytes)
    assert content_bytes == body_text.encode("utf-8")
    
    # Test with binary content
    req = SimpleNamespace(
        url="https://example.com/video.ts",
        headers={"User-Agent": "pytest"},
        method="GET",
        body=None,
    )
    body_bytes = b"\x00\x01\x02\x03"
    response = SimpleNamespace(
        text=None,
        content=body_bytes,
        request=req,
        headers={"Content-Type": "video/mp2t"},
        status_code=200,
        reason="OK",
        elapsed=timedelta(milliseconds=5),
    )
    entry = RequestsResponseTraceEntry(response)
    assert isinstance(entry.content_bytes, bytes)
    assert entry.content_bytes == body_bytes
    
    # Test with empty content
    response = _fake_response(body="")
    entry = RequestsResponseTraceEntry(response)
    assert entry.content_bytes == b""
