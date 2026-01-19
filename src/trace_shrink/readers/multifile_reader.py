from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from zipfile import ZipFile

from ..entries.multifile_entry import MultiFileTraceEntry
from ..trace import Trace
from .trace_reader import TraceReader


class MultiFileFolderReader(TraceReader):
    """TraceReader backed by a folder or .barc/.zip archive containing request_N.meta.json and request_N.body files.
    
    Supports both:
    - Directory path containing multifile format files
    - .barc or .zip archive containing multifile format files
    """

    META_RE = re.compile(r"request_(\d+)\.meta\.json$")

    def __init__(self, path: str):
        """Initialize reader with path to folder or .barc/.zip archive.
        
        Args:
            path: Path to either a directory or a .barc/.zip file
        """
        super().__init__()
        self.path = path
        self._entries_loaded = False

    @property
    def trace(self) -> Trace:
        """Lazy-load entries when trace is accessed."""
        if not self._entries_loaded:
            entries = self._load_entries()
            self._trace.extend(entries)
            self._entries_loaded = True
        return self._trace

    def _load_entries(self) -> List[MultiFileTraceEntry]:
        """Load entries from either folder or archive."""
        path_obj = Path(self.path)
        
        if path_obj.is_dir():
            return self._scan_folder(path_obj)
        elif path_obj.is_file() and path_obj.suffix.lower() in ('.barc', '.zip'):
            return self._scan_archive(path_obj)
        else:
            return []

    def _scan_folder(self, folder_path: Path) -> List[MultiFileTraceEntry]:
        """Scan a folder for multifile entries (checks root and 'requests' subdirectory)."""
        # Check the folder itself and the 'requests' subdirectory if it exists
        dirs_to_check = [folder_path]
        requests_dir = folder_path / "requests"
        if requests_dir.is_dir():
            dirs_to_check.append(requests_dir)
        
        # Find all .meta.json files in these directories
        meta_files = []
        for dir_path in dirs_to_check:
            for f in dir_path.iterdir():
                if f.is_file() and f.name.endswith(".meta.json"):
                    meta_files.append(f)
        
        metas = []
        for meta_path in meta_files:
            m = self.META_RE.search(meta_path.name)
            if m:
                idx = int(m.group(1))
                idx_str = m.group(1)
                metas.append((idx, meta_path, idx_str))

        metas.sort()
        entries: List[MultiFileTraceEntry] = []
        for idx, meta_path, idx_str in metas:
            # Look for body and annotation files in the same directory as the meta file
            parent_dir = meta_path.parent
            
            # possible body files: request_{idx_str}.body* (any extension)
            body_path = None
            prefix = f"request_{idx_str}.body"
            for f in parent_dir.iterdir():
                if f.is_file() and f.name.startswith(prefix):
                    body_path = f
                    break

            # annotations: request_{idx_str}.*.txt (e.g., request_000001.digest.txt)
            ann_paths = []
            ann_prefix = f"request_{idx_str}."
            for f in parent_dir.iterdir():
                if f.is_file() and f.name.startswith(ann_prefix) and f.name.endswith(".txt") and f != meta_path:
                    # Skip the meta.json file, only include .txt annotation files
                    ann_paths.append(str(f))

            entry = MultiFileTraceEntry.from_files(
                idx, str(meta_path), str(body_path) if body_path else "", ann_paths
            )
            entries.append(entry)

        return entries

    def _scan_archive(self, archive_path: Path) -> List[MultiFileTraceEntry]:
        """Scan a .barc/.zip archive for multifile entries."""
        entries: List[MultiFileTraceEntry] = []
        
        with ZipFile(archive_path, 'r') as zf:
            # Get list of all files in archive
            file_list = zf.namelist()
            
            # Find all meta files
            metas = []
            for filename in file_list:
                # Strip any directory prefix to get just the filename
                basename = Path(filename).name
                m = self.META_RE.search(basename)
                if m:
                    idx = int(m.group(1))
                    idx_str = m.group(1)
                    metas.append((idx, filename, idx_str))
            
            metas.sort()
            
            for idx, meta_filename, idx_str in metas:
                # Read meta JSON
                meta_data = zf.read(meta_filename)
                exchange = json.loads(meta_data.decode('utf-8'))
                
                # Find corresponding body file
                body_bytes: Optional[bytes] = None
                body_prefix = f"request_{idx_str}.body"
                meta_dir = str(Path(meta_filename).parent)
                
                for filename in file_list:
                    basename = Path(filename).name
                    # Check if file is in same directory as meta and matches body pattern
                    file_dir = str(Path(filename).parent)
                    if file_dir == meta_dir and basename.startswith(body_prefix):
                        try:
                            body_bytes = zf.read(filename)
                        except Exception:
                            body_bytes = None
                        break
                
                # Find annotation files
                annotations: Dict[str, str] = {}
                ann_prefix = f"request_{idx_str}."
                for filename in file_list:
                    basename = Path(filename).name
                    file_dir = str(Path(filename).parent)
                    if (file_dir == meta_dir and 
                        basename.startswith(ann_prefix) and 
                        basename.endswith(".txt") and 
                        basename != Path(meta_filename).name):
                        try:
                            ann_data = zf.read(filename).decode('utf-8')
                            # Extract annotation name
                            ann_m = re.match(r"^request_\d+\.(.+)\.txt$", basename)
                            ann_name = ann_m.group(1) if ann_m else basename.replace(".txt", "")
                            annotations[ann_name] = ann_data
                        except Exception:
                            pass
                
                # Create entry directly from data (not files)
                entry = MultiFileTraceEntry(idx, exchange, body_bytes, annotations)
                entries.append(entry)
        
        return entries
