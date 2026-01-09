import os

from .archive_reader import ArchiveReader
from .bodylogger_reader import BodyLoggerReader
from .har_reader import HarReader
from .proxyman_log_reader import ProxymanLogV2Reader


def open_archive(path: str) -> ArchiveReader:
    """
    Factory function to open a trace file and return the correct ArchiveReader subclass.
    Supports .har, .proxymanlogv2, and .log (bodylogger) files.
    
    Raises ValueError for unknown/unsupported file formats.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".har":
        return HarReader(path)
    elif ext == ".proxymanlogv2":
        return ProxymanLogV2Reader(path)
    elif ext == ".log":
        return BodyLoggerReader(path)
    else:
        raise ValueError(f"Unsupported trace file extension: {ext}")
