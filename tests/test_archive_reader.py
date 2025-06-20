import re
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
import yarl

from trace_shrink.archive_reader import ArchiveReader, DecoratedUrl
from trace_shrink.formats import Format
from trace_shrink.har_reader import HarReader
from trace_shrink.trace_entry import RequestDetails, ResponseDetails, TraceEntry


# Concrete implementation of ArchiveReader for testing
class MockArchiveReader(ArchiveReader):
    def __init__(self, entries: list[TraceEntry]):
        super().__init__()  # Initialize parent class to set up indexes
        self._entries = entries

    @property
    def entries(self) -> list[TraceEntry]:
        return self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)


def create_mock_entry(url_str: str, mime_type: str) -> TraceEntry:
    entry = MagicMock(spec=TraceEntry)
    entry.request = MagicMock(spec=RequestDetails)
    entry.request.url = yarl.URL(url_str)
    entry.response = MagicMock(spec=ResponseDetails)
    entry.response.mime_type = mime_type
    return entry


class TestArchiveReaderGetAbrManifestUrls:
    def test_get_abr_manifest_urls_empty_archive(self):
        reader = MockArchiveReader(entries=[])
        assert reader.get_abr_manifest_urls() == []

    def test_get_abr_manifest_urls_no_abr_manifests(self):
        entries = [
            create_mock_entry("http://example.com/video.mp4", "video/mp4"),
            create_mock_entry("http://example.com/image.jpg", "image/jpeg"),
        ]
        reader = MockArchiveReader(entries=entries)
        assert reader.get_abr_manifest_urls() == []

    def test_get_abr_manifest_urls_one_hls_manifest(self):
        hls_url = yarl.URL("http://example.com/master.m3u8")
        entries = [
            create_mock_entry(str(hls_url), "application/vnd.apple.mpegurl"),
            create_mock_entry("http://example.com/video.mp4", "video/mp4"),
        ]
        reader = MockArchiveReader(entries=entries)
        expected = [DecoratedUrl(hls_url, Format.HLS.value)]
        assert reader.get_abr_manifest_urls() == expected

    def test_get_abr_manifest_urls_one_dash_manifest_by_mime(self):
        dash_url = yarl.URL("http://example.com/manifest.mpd")
        entries = [
            create_mock_entry(str(dash_url), "application/dash+xml"),
            create_mock_entry("http://example.com/video.mp4", "video/mp4"),
        ]
        reader = MockArchiveReader(entries=entries)
        expected = [DecoratedUrl(dash_url, Format.DASH.value)]
        assert reader.get_abr_manifest_urls() == expected

    def test_get_abr_manifest_urls_one_dash_manifest_by_extension(self):
        dash_url = yarl.URL("http://example.com/manifest.mpd")
        entries = [
            # Mime type is generic, but .mpd extension implies DASH
            create_mock_entry(str(dash_url), "application/xml"),
            create_mock_entry("http://example.com/video.mp4", "video/mp4"),
        ]
        reader = MockArchiveReader(entries=entries)
        expected = [DecoratedUrl(dash_url, Format.DASH.value)]
        assert reader.get_abr_manifest_urls() == expected

    def test_get_abr_manifest_urls_one_hls_manifest_by_extension(self):
        hls_url = yarl.URL("http://example.com/playlist.m3u8")
        entries = [
            # Mime type is generic, but .m3u8 extension implies HLS
            create_mock_entry(str(hls_url), "application/octet-stream"),
            create_mock_entry("http://example.com/video.mp4", "video/mp4"),
        ]
        reader = MockArchiveReader(entries=entries)
        expected = [DecoratedUrl(hls_url, Format.HLS.value)]
        assert reader.get_abr_manifest_urls() == expected

    def test_get_abr_manifest_urls_multiple_abr_manifests(self):
        hls_url = yarl.URL("http://example.com/master.m3u8")
        dash_url = yarl.URL("http://example.com/manifest.mpd")
        another_hls_url = yarl.URL("http://example.com/another.m3u8")
        entries = [
            create_mock_entry(str(hls_url), "application/vnd.apple.mpegurl"),
            create_mock_entry(str(dash_url), "application/dash+xml"),
            create_mock_entry(str(another_hls_url), "audio/mpegurl"),  # Another HLS
        ]
        reader = MockArchiveReader(entries=entries)
        expected_set = {  # Use a set for order-agnostic comparison
            DecoratedUrl(hls_url, Format.HLS.value),
            DecoratedUrl(dash_url, Format.DASH.value),
            DecoratedUrl(another_hls_url, Format.HLS.value),
        }
        actual_result = reader.get_abr_manifest_urls()
        assert len(actual_result) == len(expected_set)
        assert set(actual_result) == expected_set

    def test_get_abr_manifest_urls_mixed_entries(self):
        hls_url = yarl.URL("http://example.com/master.m3u8")
        entries = [
            create_mock_entry("http://example.com/video.mp4", "video/mp4"),
            create_mock_entry(str(hls_url), "application/vnd.apple.mpegurl"),
            create_mock_entry("http://example.com/image.jpg", "image/jpeg"),
        ]
        reader = MockArchiveReader(entries=entries)
        expected = [DecoratedUrl(hls_url, Format.HLS.value)]
        assert reader.get_abr_manifest_urls() == expected

    def test_get_abr_manifest_urls_url_object_passed_correctly(self):
        # Ensures that the yarl.URL object from the entry is passed, not a string
        hls_url_obj = yarl.URL("http://example.com/master.m3u8")

        entry_mock = MagicMock(spec=TraceEntry)
        entry_mock.request = MagicMock(spec=RequestDetails)
        # Crucially, request.url is already a yarl.URL object
        type(entry_mock.request).url = PropertyMock(return_value=hls_url_obj)

        entry_mock.response = MagicMock(spec=ResponseDetails)
        entry_mock.response.mime_type = "application/vnd.apple.mpegurl"

        reader = MockArchiveReader(entries=[entry_mock])
        result = reader.get_abr_manifest_urls()

        assert len(result) == 1
        assert result[0].url is hls_url_obj  # Check for object identity
        assert result[0].format == Format.HLS.value

    def test_get_abr_manifest_urls_from_real_har_file(self):
        """Test get_abr_manifest_urls with a real HAR file."""
        har_file_path = Path(__file__).parent / "archives" / "export-proxyman.har"
        assert har_file_path.exists(), f"HAR file not found at {har_file_path}"

        reader = HarReader(str(har_file_path))

        # All manifest-like URLs in this file are HLS.
        expected_urls_formats_set = {  # Using a set for order-agnostic comparison
            DecoratedUrl(
                yarl.URL(
                    "https://ndtv24x7elemarchana.akamaized.net/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8"
                ),
                Format.HLS.value,
            ),
            DecoratedUrl(
                yarl.URL(
                    "https://stream.broadpeak.io/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=300d1539c3b6aa17a79a8fd9f1e45448&bpkio_sessionid=10f0b15c15-19b01c4e-afbe-4590-80d1-2c3803a50505&category=all&mm_sp"
                ),
                Format.HLS.value,
            ),
            DecoratedUrl(
                yarl.URL("https://ajo.prod.reuters.tv/v3/playlist/691410/master.m3u8"),
                Format.HLS.value,
            ),
            DecoratedUrl(
                yarl.URL(
                    "https://ajo.prod.reuters.tv/v3/playlist/320x180/691410/rendition.m3u8"
                ),
                Format.HLS.value,
            ),
            DecoratedUrl(
                yarl.URL(
                    "https://ajo.prod.reuters.tv/v3/playlist/640x360/691410/rendition.m3u8"
                ),
                Format.HLS.value,
            ),
        }

        actual_urls = reader.get_abr_manifest_urls()

        assert len(actual_urls) == len(expected_urls_formats_set), (
            f"Expected {len(expected_urls_formats_set)} manifest URLs, but got {len(actual_urls)}"
        )
        assert set(actual_urls) == expected_urls_formats_set, (
            "The set of returned URLs and formats does not match the expected set."
        )

        actual_hls_urls = reader.get_abr_manifest_urls(format=Format.HLS)
        assert len(actual_hls_urls) == len(expected_urls_formats_set), (
            f"Expected {len(expected_urls_formats_set)} HLS manifest URLs, but got {len(actual_hls_urls)}"
        )
        assert set(actual_hls_urls) == expected_urls_formats_set, (
            "The set of returned URLs and formats does not match the expected set."
        )

        actual_dash_urls = reader.get_abr_manifest_urls(format=Format.DASH)
        assert len(actual_dash_urls) == 0, (
            f"Expected {len(expected_urls_formats_set)} DASH manifest URLs, but got {len(actual_dash_urls)}"
        )


class TestArchiveReaderGetEntriesForUrl:
    # --- Mock Tests ---

    def test_empty_archive(self):
        reader = MockArchiveReader(entries=[])
        assert reader.get_entries_for_url("http://example.com") == []
        assert reader.get_entries_for_partial_url("example") == []
        assert reader.get_entries_for_partial_url(re.compile("example")) == []

    # --- Exact Match Tests (mock) ---
    def test_exact_match_no_results(self):
        entries = [create_mock_entry("http://example.com/page1", "text/html")]
        reader = MockArchiveReader(entries=entries)
        assert reader.get_entries_for_url("http://example.com/page2") == []

    def test_exact_match_one_result_str_input(self):
        entry1 = create_mock_entry("http://example.com/page1", "text/html")
        entries = [entry1, create_mock_entry("http://example.com/page2", "text/html")]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_url("http://example.com/page1")
        assert result == [entry1]

    def test_exact_match_one_result_yarl_input(self):
        target_url = yarl.URL("http://example.com/page1")
        entry1 = create_mock_entry(str(target_url), "text/html")
        entries = [entry1, create_mock_entry("http://example.com/page2", "text/html")]
        reader = MockArchiveReader(entries=entries)
        # The mock implementation needs to handle yarl.URL if the main one does for url_pattern
        # For now, the main method signature is url_pattern: str | re.Pattern
        # So, we'll test by passing stringified yarl.URL to adhere to str type
        result = reader.get_entries_for_url(str(target_url))
        assert result == [entry1]

        # If ArchiveReader.get_entries_for_url allowed yarl.URL for url_pattern (and MockArchiveReader was updated):
        # reader_yarl = MockArchiveReader(entries=entries)
        # result_yarl = reader_yarl.get_entries_for_url(target_url) # Pass yarl.URL directly
        # assert result_yarl == [entry1]

    def test_exact_match_multiple_results_same_url(self):
        entry1 = create_mock_entry("http://example.com/page1", "text/html")
        entry2 = create_mock_entry("http://example.com/page1", "text/html")  # Same URL
        entry3 = create_mock_entry("http://example.com/page2", "text/html")
        entries = [entry1, entry2, entry3]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_url("http://example.com/page1")
        assert len(result) == 2
        assert entry1 in result
        assert entry2 in result

    # --- Partial Match Tests (mock) ---
    def test_partial_match_no_results(self):
        entries = [create_mock_entry("http://example.com/pageone", "text/html")]
        reader = MockArchiveReader(entries=entries)
        assert reader.get_entries_for_partial_url("pagetwo") == []

    def test_partial_match_one_result_start(self):
        entry1 = create_mock_entry("http://example.com/pageone", "text/html")
        entries = [entry1, create_mock_entry("http://foo.com/bar", "text/html")]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_partial_url("http://example.com")
        assert result == [entry1]

    def test_partial_match_one_result_middle(self):
        entry1 = create_mock_entry("http://example.com/thepageone/sub", "text/html")
        entries = [entry1, create_mock_entry("http://foo.com/bar", "text/html")]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_partial_url("thepageone")
        assert result == [entry1]

    def test_partial_match_one_result_end(self):
        entry1 = create_mock_entry("http://example.com/pageone.html", "text/html")
        entries = [entry1, create_mock_entry("http://foo.com/bar", "text/html")]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_partial_url(".html")
        assert result == [entry1]

    def test_partial_match_multiple_results(self):
        entry1 = create_mock_entry("http://example.com/page1", "text/html")
        entry2 = create_mock_entry("http://example.com/anotherpage1", "text/html")
        entry3 = create_mock_entry("http://foo.com/bar", "text/html")
        entries = [entry1, entry2, entry3]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_partial_url("page1")
        assert len(result) == 2
        assert entry1 in result
        assert entry2 in result

    # --- Regex Match Tests (mock) ---
    def test_regex_match_no_results(self):
        entries = [create_mock_entry("http://example.com/page1", "text/html")]
        reader = MockArchiveReader(entries=entries)
        assert (
            reader.get_entries_for_url(re.compile(r"page\d{2}")) == []
        )  # Expects e.g. page01

    def test_regex_match_one_result(self):
        entry1 = create_mock_entry(
            "http://example.com/resource/id123/data", "application/json"
        )
        entries = [
            entry1,
            create_mock_entry("http://example.com/resource/idABC/data", "text/html"),
        ]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_partial_url(re.compile(r"/id\d+/"))
        assert result == [entry1]

    def test_regex_match_multiple_results(self):
        entry1 = create_mock_entry("http://example.com/img_001.png", "image/png")
        entry2 = create_mock_entry("http://example.com/img_002.png", "image/png")
        entry3 = create_mock_entry("http://example.com/image_abc.jpg", "image/jpeg")
        entries = [entry1, entry2, entry3]
        reader = MockArchiveReader(entries=entries)
        result = reader.get_entries_for_partial_url(re.compile(r"img_\d{3}\.png$"))
        assert len(result) == 2
        assert entry1 in result
        assert entry2 in result

    def test_regex_match_partial_match_flag_ignored(self):
        entry1 = create_mock_entry("http://example.com/data", "text/plain")
        entries = [entry1]
        reader = MockArchiveReader(entries=entries)
        pattern = re.compile("data")
        # partial_match=True should not change regex behavior (which is inherently partial via search)
        result_true = reader.get_entries_for_partial_url(pattern)
        # partial_match=False should also not change regex behavior
        result_false = reader.get_entries_for_partial_url(pattern)
        assert result_true == [entry1]
        assert result_false == [entry1]

    # --- Real HAR File Tests ---
    @pytest.fixture(scope="class")
    def har_reader(self):
        har_file_path = Path(__file__).parent / "archives" / "export-proxyman.har"
        assert har_file_path.exists(), f"HAR file not found at {har_file_path}"
        return HarReader(str(har_file_path))

    # --- Exact Match Tests (real HAR) ---
    def test_real_har_exact_match_multiple_occurrences(self, har_reader):
        url_to_find = "https://ndtv24x7elemarchana.akamaized.net/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8"
        expected_count = 7

        result = har_reader.get_entries_for_url(url_to_find)
        assert len(result) == expected_count
        for entry in result:
            assert str(entry.request.url) == url_to_find

    def test_real_har_exact_match_with_query_params(self, har_reader):
        url_to_find = "https://stream.broadpeak.io/hls/live/2003678/ndtv24x7/masterp_360p@1.m3u8?bpkio_serviceid=300d1539c3b6aa17a79a8fd9f1e45448&bpkio_sessionid=10f0b15c15-19b01c4e-afbe-4590-80d1-2c3803a50505&category=all&mm_sp"
        # This URL also appears multiple times (e.g., _id 6559, 6567, 6671, ...)
        # Counted 7 occurrences for this one too.
        expected_count = 7
        result = har_reader.get_entries_for_url(url_to_find)
        assert len(result) == expected_count
        for entry in result:
            assert str(entry.request.url) == url_to_find

    def test_real_har_exact_match_single_occurrence(self, har_reader):
        url_to_find = "https://ajo.prod.reuters.tv/v3/playlist/691410/master.m3u8"
        # This URL (_id 6740) should appear once.
        expected_count = 1
        result = har_reader.get_entries_for_url(url_to_find)
        assert len(result) == expected_count
        assert str(result[0].request.url) == url_to_find

    def test_real_har_exact_match_not_exists(self, har_reader):
        url_to_find = "http://nonexistent.example.com/manifest.m3u8"
        result = har_reader.get_entries_for_url(url_to_find)
        assert len(result) == 0

    # --- Partial Match Tests (real HAR) ---
    def test_real_har_partial_match_multiple_occurrences_host(self, har_reader):
        partial_url_pattern = "akamaized.net"
        # Expect many ndtv24x7elemarchana.akamaized.net URLs. All 17 from get_abr_manifest_urls are not from akamaized.
        # The 5 unique URLs from get_abr_manifest_urls are:
        # 1. ndtv24x7elemarchana.akamaized.net (appears multiple times)
        # 2. stream.broadpeak.io (appears multiple times)
        # 3. ajo.prod.reuters.tv (master, 320x180, 640x360 renditions)
        # From HAR _ids 6558, 6566, 6654, 6686, 6791, 7222, 7439 are *.akamaized.net (7 entries)
        expected_min_count = 7
        result = har_reader.get_entries_for_partial_url(partial_url_pattern)
        assert len(result) >= expected_min_count
        for entry in result:
            assert partial_url_pattern in str(entry.request.url)

    def test_real_har_partial_match_query_param_key(self, har_reader):
        partial_url_pattern = "bpkio_serviceid="
        # All stream.broadpeak.io URLs have this. There are 7 such unique URLs for manifests.
        # And each is repeated. (7 manifest URLs as per test_get_abr_manifest_urls_from_real_har_file)
        # The actual count of entries with this substring is 7 (from _id 6559, 6567, 6671, 6709, 6894, 7141, 7292)
        expected_count = 7
        result = har_reader.get_entries_for_partial_url(partial_url_pattern)
        assert len(result) == expected_count
        for entry in result:
            assert partial_url_pattern in str(entry.request.url)

    def test_real_har_partial_match_path_segment(self, har_reader):
        partial_url_pattern = "reuters.tv/v3/playlist/"
        # Matches _id 6740 (master), 6743 (320x180), 6748 (640x360) -> 3 entries.
        expected_count = 3
        result = har_reader.get_entries_for_partial_url(partial_url_pattern)
        assert len(result) == expected_count
        for entry in result:
            assert partial_url_pattern in str(entry.request.url)

    def test_real_har_partial_match_not_exists(self, har_reader):
        partial_url_pattern = "thisstringshouldnotbeintheurls"
        result = har_reader.get_entries_for_partial_url(partial_url_pattern)
        assert len(result) == 0

    # --- Regex Match Tests (real HAR) ---
    def test_real_har_regex_match_m3u8_files(self, har_reader):
        # Matches any URL ending with .m3u8 possibly with query parameters
        regex_pattern = re.compile(r"\.m3u8($|\?)")
        # All 17 manifest URLs found by get_abr_manifest_urls end this way.
        # Since get_abr_manifest_urls returns unique URLs (5 of them),
        # this regex should match all entries that correspond to these manifests.
        # The total number of such manifest entries is 17 in this HAR file.
        expected_count = 17
        result = har_reader.get_entries_for_partial_url(regex_pattern)
        assert len(result) == expected_count
        for entry in result:
            assert regex_pattern.search(str(entry.request.url))

    def test_real_har_regex_match_reuters_master(self, har_reader):
        regex_pattern = re.compile(r"ajo\.prod\.reuters\.tv/.*/master\.m3u8")
        # Matches _id 6740
        expected_count = 1
        result = har_reader.get_entries_for_partial_url(regex_pattern)
        assert len(result) == expected_count
        assert regex_pattern.search(str(result[0].request.url))

    def test_real_har_regex_match_reuters_renditions(self, har_reader):
        regex_pattern = re.compile(r"ajo\.prod\.reuters\.tv/.*/rendition\.m3u8")
        # Matches _id 6743, 6748
        expected_count = 2
        result = har_reader.get_entries_for_partial_url(regex_pattern)
        assert len(result) == expected_count
        for entry in result:
            assert regex_pattern.search(str(entry.request.url))

    def test_real_har_regex_match_broadpeak_with_session(self, har_reader):
        regex_pattern = re.compile(r"stream\.broadpeak\.io/.*bpkio_sessionid=")
        # All 7 broadpeak.io manifest entries should match this.
        expected_count = 7
        result = har_reader.get_entries_for_partial_url(regex_pattern)
        assert len(result) == expected_count
        for entry in result:
            assert regex_pattern.search(str(entry.request.url))

    def test_real_har_regex_match_not_exists(self, har_reader):
        regex_pattern = re.compile(r"nonexistentdomain\.com/.*\.mpd$")
        result = har_reader.get_entries_for_url(regex_pattern)
        assert len(result) == 0
