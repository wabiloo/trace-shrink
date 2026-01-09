"""
Tests for the Exporter class and cross-format conversion.
"""

import json
import tempfile
from pathlib import Path

import pytest

from trace_shrink import (
    Exporter,
    HarReader,
    ProxymanLogV2Reader,
)


@pytest.fixture(scope="module")
def har_file_path() -> Path:
    """Path to a test HAR file."""
    path = Path(__file__).parent / "archives" / "hls1-chrome.har"
    if not path.exists():
        pytest.skip(f"HAR file not found: {path}")
    return path


@pytest.fixture(scope="module")
def proxyman_file_path() -> Path:
    """Path to a test Proxyman log file."""
    path = Path(__file__).parent / "archives" / "hls1-proxyman.proxymanlogv2"
    if not path.exists():
        pytest.skip(f"Proxyman log file not found: {path}")
    return path


@pytest.fixture(scope="module")
def har_reader(har_file_path: Path) -> HarReader:
    """Create a HarReader instance."""
    return HarReader(str(har_file_path))


@pytest.fixture(scope="module")
def proxyman_reader(proxyman_file_path: Path) -> ProxymanLogV2Reader:
    """Create a ProxymanLogV2Reader instance."""
    return ProxymanLogV2Reader(str(proxyman_file_path))


class TestExporterClassMethods:
    """Tests for Exporter class methods (direct export with entries)."""

    def test_to_har_class_method(self, har_reader: HarReader):
        """Test exporting entries to HAR using class method."""
        entries = har_reader.entries[:3]  # Get first 3 entries

        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            Exporter.to_har(output_path, entries)

            # Verify the file was created and is valid JSON
            assert Path(output_path).exists()
            with open(output_path, "r") as f:
                har_data = json.load(f)

            # Verify structure
            assert "log" in har_data
            assert "entries" in har_data["log"]
            assert len(har_data["log"]["entries"]) == 3

            # Verify entries match
            for i, entry in enumerate(entries):
                har_entry = har_data["log"]["entries"][i]
                assert har_entry["request"]["url"] == str(entry.request.url)
                assert har_entry["request"]["method"] == entry.request.method
                assert har_entry["response"]["status"] == entry.response.status_code

        finally:
            Path(output_path).unlink()

    def test_to_proxyman_class_method(self, har_reader: HarReader):
        """Test exporting entries to Proxyman using class method."""
        entries = har_reader.entries[:2]  # Get first 2 entries

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".proxymanlogv2", delete=False
        ) as f:
            output_path = f.name

        try:
            Exporter.to_proxyman(output_path, entries)

            # Verify the file was created
            assert Path(output_path).exists()

            # Verify it's a valid ZIP archive
            import zipfile

            with zipfile.ZipFile(output_path, "r") as zip_ref:
                file_list = zip_ref.namelist()
                assert len(file_list) == 2

                # Verify entries
                for i, entry in enumerate(entries):
                    # Find the corresponding file in the archive
                    entry_files = [
                        f for f in file_list if f.startswith(f"request_{i}_")
                    ]
                    assert len(entry_files) == 1

                    # Read and verify entry data
                    with zip_ref.open(entry_files[0]) as entry_file:
                        entry_data = json.load(entry_file)
                        assert entry_data["request"]["fullPath"] == str(
                            entry.request.url
                        )
                        assert (
                            entry_data["request"]["method"]["name"]
                            == entry.request.method
                        )
                        assert (
                            entry_data["response"]["status"]["code"]
                            == entry.response.status_code
                        )

        finally:
            Path(output_path).unlink()


class TestExporterInstanceMethods:
    """Tests for Exporter instance methods (with ArchiveReader)."""

    def test_to_har_instance_method_all_entries(self, har_reader: HarReader):
        """Test exporting all entries using instance method."""
        exporter = Exporter(har_reader)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            exporter.to_har(output_path)

            # Verify all entries were exported
            with open(output_path, "r") as f:
                har_data = json.load(f)

            assert len(har_data["log"]["entries"]) == len(har_reader.entries)

        finally:
            Path(output_path).unlink()

    def test_to_har_instance_method_filtered_entries(self, har_reader: HarReader):
        """Test exporting filtered entries using instance method."""
        exporter = Exporter(har_reader)
        filtered_entries = har_reader.entries[:2]  # First 2 entries

        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            exporter.to_har(output_path, filtered_entries)

            # Verify only filtered entries were exported
            with open(output_path, "r") as f:
                har_data = json.load(f)

            assert len(har_data["log"]["entries"]) == 2

        finally:
            Path(output_path).unlink()

    def test_to_proxyman_instance_method_all_entries(
        self, proxyman_reader: ProxymanLogV2Reader
    ):
        """Test exporting all entries to Proxyman using instance method."""
        exporter = Exporter(proxyman_reader)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".proxymanlogv2", delete=False
        ) as f:
            output_path = f.name

        try:
            exporter.to_proxyman(output_path)

            # Verify all entries were exported
            import zipfile

            with zipfile.ZipFile(output_path, "r") as zip_ref:
                assert len(zip_ref.namelist()) == len(proxyman_reader.entries)

        finally:
            Path(output_path).unlink()


class TestCrossFormatConversion:
    """Tests for cross-format conversion (HAR <-> Proxyman)."""

    def test_har_to_proxyman_conversion(self, har_reader: HarReader):
        """Test converting HAR entries to Proxyman format."""
        entries = har_reader.entries[:3]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".proxymanlogv2", delete=False
        ) as f:
            output_path = f.name

        try:
            Exporter.to_proxyman(output_path, entries)

            # Verify conversion by reading back
            reader = ProxymanLogV2Reader(output_path)
            assert len(reader.entries) == 3

            # Verify data integrity
            for i, original_entry in enumerate(entries):
                converted_entry = reader.entries[i]
                assert str(converted_entry.request.url) == str(
                    original_entry.request.url
                )
                assert converted_entry.request.method == original_entry.request.method
                assert (
                    converted_entry.response.status_code
                    == original_entry.response.status_code
                )

        finally:
            Path(output_path).unlink()

    def test_har_to_proxyman_conversion_with_highlight(self, har_reader: HarReader):
        """Test converting HAR entries with highlight to Proxyman format."""
        entries = har_reader.entries[:2]

        # Set highlights on HAR entries
        entries[0].set_highlight("red")
        entries[1].set_highlight("strike")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".proxymanlogv2", delete=False
        ) as f:
            output_path = f.name

        try:
            Exporter.to_proxyman(output_path, entries)

            # Verify conversion by reading back
            reader = ProxymanLogV2Reader(output_path)
            assert len(reader.entries) == 2

            # Verify highlights were converted correctly
            assert reader.entries[0]._raw_data["style"]["color"] == 0  # red
            assert reader.entries[1]._raw_data["style"]["textStyle"] == 0  # strike

        finally:
            Path(output_path).unlink()

    def test_proxyman_to_har_conversion(self, proxyman_reader: ProxymanLogV2Reader):
        """Test converting Proxyman entries to HAR format."""
        entries = proxyman_reader.entries[:3]
        num_entries = len(entries)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            Exporter.to_har(output_path, entries)

            # Verify conversion by reading back
            reader = HarReader(output_path)
            assert len(reader.entries) == num_entries

            # Verify data integrity
            for i, original_entry in enumerate(entries):
                converted_entry = reader.entries[i]
                assert str(converted_entry.request.url) == str(
                    original_entry.request.url
                )
                assert converted_entry.request.method == original_entry.request.method
                assert (
                    converted_entry.response.status_code
                    == original_entry.response.status_code
                )

        finally:
            Path(output_path).unlink()

    def test_round_trip_conversion(self, har_reader: HarReader):
        """Test HAR -> Proxyman -> HAR round trip conversion."""
        original_entries = har_reader.entries[:2]

        with tempfile.TemporaryDirectory() as tmpdir:
            proxyman_path = Path(tmpdir) / "intermediate.proxymanlogv2"
            final_har_path = Path(tmpdir) / "final.har"

            # HAR -> Proxyman
            Exporter.to_proxyman(str(proxyman_path), original_entries)

            # Proxyman -> HAR
            proxyman_reader = ProxymanLogV2Reader(str(proxyman_path))
            Exporter.to_har(str(final_har_path), proxyman_reader.entries)

            # Verify final HAR
            final_reader = HarReader(str(final_har_path))
            assert len(final_reader.entries) == 2

            # Verify data integrity
            for i, original_entry in enumerate(original_entries):
                final_entry = final_reader.entries[i]
                assert str(final_entry.request.url) == str(original_entry.request.url)
                assert final_entry.request.method == original_entry.request.method
                assert (
                    final_entry.response.status_code
                    == original_entry.response.status_code
                )


class TestExporterWithFiltering:
    """Tests for Exporter with filtered entries."""

    def test_export_filtered_by_host(self, har_reader: HarReader):
        """Test exporting entries filtered by host."""
        exporter = Exporter(har_reader)

        # Filter entries by host
        filtered_entries = har_reader.filter(host="stream.broadpeak.io")

        if filtered_entries:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".har", delete=False
            ) as f:
                output_path = f.name

            try:
                exporter.to_har(output_path, filtered_entries)

                # Verify only filtered entries were exported
                with open(output_path, "r") as f:
                    har_data = json.load(f)

                assert len(har_data["log"]["entries"]) == len(filtered_entries)

            finally:
                Path(output_path).unlink()

    def test_export_filtered_by_ids(self, har_reader: HarReader):
        """Test exporting entries filtered by IDs."""
        exporter = Exporter(har_reader)

        # Get entry IDs
        entry_ids = [entry.id for entry in har_reader.entries[:3]]
        filtered_entries = har_reader.get_entries_by_ids(entry_ids)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            exporter.to_har(output_path, filtered_entries)

            # Verify correct entries were exported
            with open(output_path, "r") as f:
                har_data = json.load(f)

            assert len(har_data["log"]["entries"]) == 3

        finally:
            Path(output_path).unlink()


class TestExporterErrorHandling:
    """Tests for error handling in Exporter."""

    def test_to_har_class_method_requires_entries(self):
        """Test that class method requires entries parameter."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            # Should raise TypeError if entries not provided
            # Note: This will fail at call time with missing required argument
            import inspect

            sig = inspect.signature(Exporter.to_har)
            # Verify entries is a required parameter (no default)
            assert "entries" in sig.parameters
            assert sig.parameters["entries"].default == inspect.Parameter.empty

        finally:
            Path(output_path).unlink()

    def test_export_empty_entries_list(self, har_reader: HarReader):
        """Test exporting an empty list of entries."""
        exporter = Exporter(har_reader)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".har", delete=False) as f:
            output_path = f.name

        try:
            # Should not raise an error, just create empty HAR
            exporter.to_har(output_path, [])

            with open(output_path, "r") as f:
                har_data = json.load(f)

            assert len(har_data["log"]["entries"]) == 0

        finally:
            Path(output_path).unlink()
