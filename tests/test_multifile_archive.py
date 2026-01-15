import os
import json
import tempfile

from trace_shrink.readers import MultiFileFolderReader


def make_sample(folder, index=1, body=b"hello world", annotations=None):
    meta = {
        "timestamp": "2026-01-11T10:00:00Z",
        "request": {"url": "http://example.com/", "headers": {"User-Agent": "py"}},
        "response": {"status_code": 200, "headers": {"Content-Type": "text/plain"}},
        "elapsed_ms": 123,
    }
    meta_path = os.path.join(folder, f"request_{index}.meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    body_path = os.path.join(folder, f"request_{index}.body")
    with open(body_path, "wb") as f:
        f.write(body)

    if annotations:
        for k, v in annotations.items():
            ann_path = os.path.join(folder, f"request_{index}.{k}.txt")
            with open(ann_path, "w") as af:
                af.write(v)


def test_multifile_archive_reads_entries():
    with tempfile.TemporaryDirectory() as td:
        make_sample(td, index=1, body=b"abc", annotations={"digest": "d1"})
        make_sample(td, index=2, body=b"def")

        arch = MultiFileFolderReader(td)
        assert len(arch.trace) == 2
        entries = list(arch.trace)
        assert entries[0].index == 1
        assert entries[1].index == 2
        assert entries[0].response.status_code == 200
        assert entries[0].response.body.text.startswith("abc")


def test_multifile_archive_annotation_names():
    """Test that annotation names are extracted correctly (digest, not request_1.digest)."""
    with tempfile.TemporaryDirectory() as td:
        make_sample(td, index=1, body=b"abc", annotations={"digest": "d1", "custom": "c1"})
        make_sample(td, index=2, body=b"def", annotations={"digest": "d2"})

        arch = MultiFileFolderReader(td)
        entries = list(arch.trace)
        
        # Verify annotation keys are just the annotation name, not request_{idx}.{name}
        assert "digest" in entries[0].annotations
        assert "custom" in entries[0].annotations
        assert entries[0].annotations["digest"] == "d1"
        assert entries[0].annotations["custom"] == "c1"
        
        # Verify no keys with request_ prefix
        assert "request_1.digest" not in entries[0].annotations
        assert "request_1.custom" not in entries[0].annotations
        
        # Verify second entry
        assert "digest" in entries[1].annotations
        assert entries[1].annotations["digest"] == "d2"
        assert "request_2.digest" not in entries[1].annotations


def test_multifile_archive_annotation_names_zero_padded_index():
    """Ensure annotations are parsed correctly for request_000001.*.txt filenames."""
    with tempfile.TemporaryDirectory() as td:
        # Create a single entry with a zero-padded index
        meta = {
            "timestamp": "2026-01-11T10:00:00Z",
            "request": {"url": "http://example.com/", "method": "GET", "headers": {}},
            "response": {"status_code": 200, "headers": {"Content-Type": "text/plain"}},
            "elapsed_ms": 1,
        }
        meta_path = os.path.join(td, "request_000001.meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        body_path = os.path.join(td, "request_000001.body")
        with open(body_path, "wb") as f:
            f.write(b"abc")

        ann_path = os.path.join(td, "request_000001.digest.txt")
        with open(ann_path, "w") as f:
            f.write("d1")

        arch = MultiFileFolderReader(td)
        entries = list(arch.trace)
        assert len(entries) == 1
        assert "digest" in entries[0].annotations
        assert entries[0].annotations["digest"] == "d1"
        assert "request_000001.digest" not in entries[0].annotations


def test_multifile_archive_content_type_from_headers():
    """Test that content_type is extracted from response headers in meta.json."""
    with tempfile.TemporaryDirectory() as td:
        # Test with Content-Type in headers
        meta1 = {
            "timestamp": "2026-01-11T10:00:00Z",
            "request": {"url": "http://example.com/test.mpd", "headers": {}},
            "response": {
                "status_code": 200,
                "headers": {"Content-Type": "application/dash+xml; charset=utf-8"},
            },
            "elapsed_ms": 123,
        }
        meta_path1 = os.path.join(td, "request_1.meta.json")
        with open(meta_path1, "w") as f:
            json.dump(meta1, f)
        body_path1 = os.path.join(td, "request_1.body")
        with open(body_path1, "wb") as f:
            f.write(b"<MPD></MPD>")

        # Test without Content-Type in headers (should be None)
        meta2 = {
            "timestamp": "2026-01-11T10:00:01Z",
            "request": {"url": "http://example.com/test", "headers": {}},
            "response": {"status_code": 200, "headers": {}},
            "elapsed_ms": 124,
        }
        meta_path2 = os.path.join(td, "request_2.meta.json")
        with open(meta_path2, "w") as f:
            json.dump(meta2, f)
        body_path2 = os.path.join(td, "request_2.body")
        with open(body_path2, "wb") as f:
            f.write(b"test")

        arch = MultiFileFolderReader(td)
        entries = list(arch.trace)

        # Verify first entry has content_type and mime_type extracted from headers
        assert entries[0].response.content_type == "application/dash+xml; charset=utf-8"
        assert entries[0].response.mime_type == "application/dash+xml"

        # Verify second entry has no content_type
        assert entries[1].response.content_type is None
        assert entries[1].response.mime_type is None
