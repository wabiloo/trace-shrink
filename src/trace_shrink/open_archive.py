import os

from .archive_reader import ArchiveReader
from .har_reader import HarReader
from .proxyman_log_reader import ProxymanLogV2Reader


def open_archive(path: str) -> ArchiveReader:
    """
    Factory function to open a trace file and return the correct ArchiveReader subclass.
    Supports .har and .proxymanlogv2 files.
    Raises ValueError for unknown extensions.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".har":
        return HarReader(path)
    elif ext == ".proxymanlogv2":
        return ProxymanLogV2Reader(path)
    else:
        raise ValueError(f"Unsupported trace file extension: {ext}")
