import pytest
import yarl

from trace_shrink.formats import Format, MimeType


@pytest.mark.parametrize(
    "mime_type, format, expected",
    [
        ("application/vnd.apple.mpegurl", Format.HLS, True),
        ("application/x-mpegurl", Format.HLS, True),
        ("application/dash+xml", Format.DASH, True),
        ("application/dash-xml", Format.DASH, True),
        ("application/json", Format.HLS, False),
        ("application/json", Format.DASH, False),
        ("application/vnd.apple.mpegurl;charset=UTF-8", Format.HLS, True),
    ],
)
def test_is_format(mime_type, format, expected):
    assert MimeType(mime_type).is_format(format) == expected


@pytest.mark.parametrize(
    "mime_type, expected",
    [
        ("application/dash+xml", True),
        ("application/dash-xml", True),
        ("application/vnd.apple.mpegurl", False),
        ("application/json", False),
    ],
)
def test_is_dash(mime_type, expected):
    assert MimeType(mime_type).is_dash() == expected


@pytest.mark.parametrize(
    "mime_type, expected",
    [
        ("application/vnd.apple.mpegurl", True),
        ("application/x-mpegurl", True),
        ("application/dash+xml", False),
        ("application/json", False),
    ],
)
def test_is_hls(mime_type, expected):
    assert MimeType(mime_type).is_hls() == expected


@pytest.mark.parametrize(
    "mime_type, expected",
    [
        ("application/vnd.apple.mpegurl", True),
        ("application/dash+xml", True),
        ("application/json", False),
    ],
)
def test_is_abr_manifest(mime_type, expected):
    assert MimeType(mime_type).is_abr_manifest() == expected


@pytest.mark.parametrize(
    "mime_type, expected",
    [
        ("application/vnd.apple.mpegurl", True),
        ("application/dash+xml", True),
        ("text/plain", False),
        ("application/json", False),
    ],
)
def test_has_text_content(mime_type, expected):
    assert MimeType(mime_type).has_text_content() == expected


@pytest.mark.parametrize(
    "mime_type, expected",
    [
        ("application/vnd.apple.mpegurl", Format.HLS),
        ("application/x-mpegurl", Format.HLS),
        ("application/dash+xml", Format.DASH),
        ("application/dash-xml", Format.DASH),
        ("application/json", None),
    ],
)
def test_to_format(mime_type, expected):
    assert MimeType(mime_type).to_format() == expected


@pytest.mark.parametrize(
    "extension, expected",
    [
        ("m3u8", Format.HLS),
        ("mpd", Format.DASH),
        ("ts", None),
        ("mp4", None),
    ],
)
def test_format_from_extension(extension, expected):
    assert Format.from_extension(extension) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://example.com/master.m3u8", Format.HLS),
        ("http://example.com/manifest.mpd", Format.DASH),
        ("http://example.com/segment.ts", None),
        ("http://example.com/video.mp4", None),
        ("http://example.com/path/to/file.m3u8?query=param", Format.HLS),
    ],
)
def test_format_from_url(url, expected):
    assert Format.from_url(yarl.URL(url)) == expected


@pytest.mark.parametrize(
    "url_path, expected",
    [
        ("/master.m3u8", Format.HLS),
        ("/manifest.mpd", Format.DASH),
        ("segment.ts", None),
        ("video.mp4", None),
        ("/path/to/file.m3u8", Format.HLS),
    ],
)
def test_format_from_path(url_path, expected):
    assert Format.from_path(url_path) == expected


@pytest.mark.parametrize(
    "mime_type, url, expected",
    [
        ("application/vnd.apple.mpegurl", "http://example.com/master.m3u8", Format.HLS),
        ("application/dash+xml", "http://example.com/manifest.mpd", Format.DASH),
        (
            "application/octet-stream",
            "http://example.com/master.m3u8",
            Format.HLS,
        ),
        ("application/octet-stream", "http://example.com/manifest.mpd", Format.DASH),
        ("application/json", "http://example.com/data.json", None),
    ],
)
def test_format_from_url_or_mime_type(mime_type, url, expected):
    assert Format.from_url_or_mime_type(mime_type, yarl.URL(url)) == expected
