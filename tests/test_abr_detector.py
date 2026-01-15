from unittest.mock import MagicMock, PropertyMock

import pytest
import yarl

from trace_shrink import (
    DecoratedUrl,
    Format,
    Trace,
)
from trace_shrink.entries import TraceEntry, RequestDetails, ResponseDetails
from trace_shrink.abr import AbrDetector
from trace_shrink.entries import TraceEntry, RequestDetails, ResponseDetails

def create_mock_entry(url_str: str, mime_type: str, entry_id: str = None) -> TraceEntry:
    entry = MagicMock(spec=TraceEntry)
    entry.request = MagicMock(spec=RequestDetails)
    entry.request.url = yarl.URL(url_str)
    entry.response = MagicMock(spec=ResponseDetails)
    entry.response.mime_type = mime_type
    if entry_id is not None:
        type(entry).id = PropertyMock(return_value=entry_id)
    return entry


class TestAbrDetector:
    def test_init_default_ignore_params(self):
        detector = AbrDetector()
        assert detector.get_ignored_query_params() == []

    def test_ignore_query_params_single_string(self):
        detector = AbrDetector()
        result = detector.ignore_query_params("custom-param")
        assert detector.get_ignored_query_params() == ["custom-param"]
        assert result is detector  # Test method chaining

    def test_ignore_query_params_list(self):
        detector = AbrDetector()
        params = ["param1", "param2", "param3"]
        detector.ignore_query_params(params)
        assert detector.get_ignored_query_params() == params

    def test_ignore_query_params_overwrites_previous(self):
        detector = AbrDetector()
        detector.ignore_query_params("param1")
        assert detector.get_ignored_query_params() == ["param1"]
        
        detector.ignore_query_params(["param2", "param3"])
        assert detector.get_ignored_query_params() == ["param2", "param3"]

    def test_method_chaining(self):
        detector = AbrDetector()
        result = detector.ignore_query_params(["param1", "param2"])
        assert result is detector


class TestTraceAbrDetectorIntegration:
    def test_trace_has_abr_detector(self):
        trace = Trace(entries=[])
        assert hasattr(trace, "abr_detector")
        assert isinstance(trace.abr_detector, AbrDetector)

    def test_custom_ignore_query_params(self):
        """Test ignoring custom query parameters."""
        manifest_url = yarl.URL("http://example.com/manifest.mpd")
        manifest_with_custom = yarl.URL("http://example.com/manifest.mpd?custom-token=abc123")
        
        entries = [
            create_mock_entry(str(manifest_url), "application/dash+xml"),
            create_mock_entry(str(manifest_with_custom), "application/dash+xml"),
        ]
        trace = Trace(entries=entries)
        
        # Configure detector to ignore custom-token instead of bk-ml
        trace.abr_detector.ignore_query_params("custom-token")
        
        result = trace.get_abr_manifest_urls()
        assert len(result) == 1
        assert result[0].url == manifest_url

    def test_ignore_multiple_query_params(self):
        """Test ignoring multiple query parameters."""
        manifest_url = yarl.URL("http://example.com/manifest.mpd")
        manifest_with_bk_ml = yarl.URL("http://example.com/manifest.mpd?bk-ml=1")
        manifest_with_token = yarl.URL("http://example.com/manifest.mpd?token=xyz")
        manifest_with_both = yarl.URL("http://example.com/manifest.mpd?bk-ml=1&token=xyz")
        
        entries = [
            create_mock_entry(str(manifest_url), "application/dash+xml"),
            create_mock_entry(str(manifest_with_bk_ml), "application/dash+xml"),
            create_mock_entry(str(manifest_with_token), "application/dash+xml"),
            create_mock_entry(str(manifest_with_both), "application/dash+xml"),
        ]
        trace = Trace(entries=entries)
        
        # Configure to ignore both parameters
        trace.abr_detector.ignore_query_params(["bk-ml", "token"])
        
        result = trace.get_abr_manifest_urls()
        assert len(result) == 1
        assert result[0].url == manifest_url

    def test_ignore_empty_list(self):
        """Test that passing empty list ignores no parameters."""
        manifest_with_bk_ml = yarl.URL("http://example.com/manifest.mpd?bk-ml=1")
        
        entries = [
            create_mock_entry(str(manifest_with_bk_ml), "application/dash+xml"),
        ]
        trace = Trace(entries=entries)
        
        # Configure to ignore nothing
        trace.abr_detector.ignore_query_params([])
        
        result = trace.get_abr_manifest_urls()
        assert len(result) == 1
        assert result[0].url == manifest_with_bk_ml

    def test_ignore_nonexistent_parameter(self):
        """Test ignoring a parameter that doesn't exist."""
        manifest_url = yarl.URL("http://example.com/manifest.mpd")
        
        entries = [
            create_mock_entry(str(manifest_url), "application/dash+xml"),
        ]
        trace = Trace(entries=entries)
        
        # Configure to ignore a parameter that doesn't exist
        trace.abr_detector.ignore_query_params("nonexistent")
        
        result = trace.get_abr_manifest_urls()
        assert len(result) == 1
        assert result[0].url == manifest_url

    def test_parameter_with_no_value(self):
        """Test that parameter presence is checked even without value."""
        manifest_url = yarl.URL("http://example.com/manifest.mpd")
        manifest_with_param = yarl.URL("http://example.com/manifest.mpd?ding")
        
        entries = [
            create_mock_entry(str(manifest_url), "application/dash+xml"),
            create_mock_entry(str(manifest_with_param), "application/dash+xml"),
        ]
        trace = Trace(entries=entries)
        trace.abr_detector.ignore_query_params("ding")
        
        result = trace.get_abr_manifest_urls()
        assert len(result) == 1
        assert result[0].url == manifest_url
