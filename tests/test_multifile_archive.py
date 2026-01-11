import os
import json
import tempfile

from trace_shrink.multifile_reader import MultiFileFolderArchive


def make_sample(folder, index=1, body=b"hello world", annotations=None):
    meta = {
        "timestamp": "2026-01-11T10:00:00Z",
        "request": {"url": "http://example.com/", "headers": {"User-Agent": "py"}},
        "response": {"status_code": 200, "headers": {"Content-Type": "text/plain"}},
        "facets": {},
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

        arch = MultiFileFolderArchive(td)
        assert len(arch) == 2
        entries = list(arch)
        assert entries[0].index == 1
        assert entries[1].index == 2
        assert entries[0].response.status_code == 200
        assert entries[0].response.body.text.startswith("abc")
