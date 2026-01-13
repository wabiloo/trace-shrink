from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import List

from ..entries.multifile_entry import MultiFileTraceEntry
from .trace_reader import TraceReader


class MultiFileFolderArchive(TraceReader):
    """TraceReader backed by a folder containing request_N.meta.json and request_N.body files."""

    META_RE = re.compile(r"request_(\d+)\.meta\.json$")

    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path
        self._entries_loaded = False

    @property
    def entries(self) -> List[MultiFileTraceEntry]:
        if not self._entries_loaded:
            entries = self._scan_folder()
            self.trace.extend(entries)
            self._entries_loaded = True
        return self.trace.entries

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[MultiFileTraceEntry]:
        return iter(self.trace)

    def _scan_folder(self) -> List[MultiFileTraceEntry]:
        if not os.path.isdir(self.folder_path):
            return []

        files = os.listdir(self.folder_path)
        metas = []
        for f in files:
            m = self.META_RE.search(f)
            if m:
                idx = int(m.group(1))
                metas.append((idx, f))

        metas.sort()
        entries: List[MultiFileTraceEntry] = []
        for idx, meta_fn in metas:
            meta_path = os.path.join(self.folder_path, meta_fn)
            # possible body files: request_{idx}.body* (any extension)
            body_path = None
            prefix = f"request_{idx}.body"
            for f in files:
                if f.startswith(prefix):
                    body_path = os.path.join(self.folder_path, f)
                    break

            # annotations: request_{idx}.digest.txt or *.txt
            ann_paths = []
            digest_candidate = os.path.join(
                self.folder_path, f"request_{idx}.digest.txt"
            )
            if os.path.exists(digest_candidate):
                ann_paths.append(digest_candidate)

            entry = MultiFileTraceEntry.from_files(
                idx, meta_path, body_path or "", ann_paths
            )
            entries.append(entry)

        return entries
