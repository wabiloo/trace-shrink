from __future__ import annotations

import re
from pathlib import Path
from typing import List

from ..entries.multifile_entry import MultiFileTraceEntry
from ..trace import Trace
from .trace_reader import TraceReader


class MultiFileFolderReader(TraceReader):
    """TraceReader backed by a folder containing request_N.meta.json and request_N.body files."""

    META_RE = re.compile(r"request_(\d+)\.meta\.json$")

    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path
        self._entries_loaded = False

    @property
    def trace(self) -> Trace:
        """Lazy-load entries when trace is accessed."""
        if not self._entries_loaded:
            entries = self._scan_folder()
            self._trace.extend(entries)
            self._entries_loaded = True
        return self._trace

    def _scan_folder(self) -> List[MultiFileTraceEntry]:
        folder_path = Path(self.folder_path)
        if not folder_path.is_dir():
            return []

        files = [f.name for f in folder_path.iterdir() if f.is_file()]
        metas = []
        for f in files:
            m = self.META_RE.search(f)
            if m:
                idx = int(m.group(1))
                # Store both the index and the actual filename prefix (for zero-padded support)
                metas.append((idx, f, m.group(1)))

        metas.sort()
        entries: List[MultiFileTraceEntry] = []
        for idx, meta_fn, idx_str in metas:
            meta_path = folder_path / meta_fn
            # possible body files: request_{idx_str}.body* (any extension)
            # Use idx_str to match zero-padded format
            body_path = None
            prefix = f"request_{idx_str}.body"
            for f in files:
                if f.startswith(prefix):
                    body_path = folder_path / f
                    break

            # annotations: request_{idx_str}.*.txt (e.g., request_000001.digest.txt)
            ann_paths = []
            ann_prefix = f"request_{idx_str}."
            for f in files:
                if f.startswith(ann_prefix) and f.endswith(".txt") and f != meta_fn:
                    # Skip the meta.json file, only include .txt annotation files
                    ann_paths.append(str(folder_path / f))

            entry = MultiFileTraceEntry.from_files(
                idx, str(meta_path), str(body_path) if body_path else "", ann_paths
            )
            entries.append(entry)

        return entries
